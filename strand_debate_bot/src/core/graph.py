from strands.memory.types import MemoryStore
from strands.models.anthropic import AnthropicModel
from strands.models.model import Model
from strands.multiagent import GraphBuilder
from strands.session.file_session_manager import FileSessionManager
from strands.session.s3_session_manager import S3SessionManager

from src.agents.con import con_opening_node, con_rebuttal_node, con_addresses_question_node, con_closing_node
from src.agents.moderator import (
    ModeratorHub,
    AudienceQuestionStub,
    AudienceQuestionHook,
    MockModeratorDecision,
    moderator_decision_node,
)
from src.agents.pro import pro_opening_node, pro_rebuttal_node, pro_addresses_question_node, pro_closing_node
from src.core import config
from src.core.config import ANTHROPIC_API_KEY, MEMORY_PERSIST_DIRECTORY, MOCK_LLM, MODEL_NAME, SESSION_STORAGE_DIRECTORY
from src.core.memory import ChromaMemoryStore, S3VectorMemoryStore
from src.core.nodes import MockTurnNode
from src.core.session import InvocationStatePersistenceHook

# The six argument turns' node id and invocation_state store_key are always
# identical (matches the old fixture JSON's own field names 1:1 -- design.md,
# Decision 6), so mock mode only needs one name per turn, not a pair.
MOCK_TURN_KEYS = ["pro_opening", "con_opening", "pro_rebuttal", "con_rebuttal", "pro_closing", "con_closing"]

# One hub visit per round (opening/rebuttal/audience/closing/done) + 9 branch
# nodes (pro/con x opening/rebuttal/audience/closing) + the decision node = 15
# executions for a full run. Set with margin rather than tuned to the exact
# count (design.md, Decision 5).
MAX_NODE_EXECUTIONS = 24


def _default_model() -> Model:
    return AnthropicModel(
        client_args={"api_key": ANTHROPIC_API_KEY},
        model_id=MODEL_NAME,
        max_tokens=1024,
    )


def default_memory_store() -> MemoryStore:
    """`S3VectorMemoryStore` when an AWS deployment target is configured,
    `ChromaMemoryStore` otherwise (deploy-to-agentcore design.md, Decision 5)."""
    if config.S3_VECTORS_BUCKET:
        return S3VectorMemoryStore(
            config.S3_VECTORS_BUCKET,
            index_name=config.S3_VECTORS_INDEX,
            embedding_model_id=config.BEDROCK_EMBEDDING_MODEL_ID,
            region_name=config.AWS_REGION,
        )
    return ChromaMemoryStore(MEMORY_PERSIST_DIRECTORY)


def _round(name: str):
    return lambda state, *, invocation_state, **kw: invocation_state.get("round") == name


def build_graph(
    model: Model | None = None,
    memory_store: MemoryStore | None = None,
    run_id: str | None = None,
    session_storage_dir: str | None = None,
    mock: bool | None = None,
):
    """Builds the debate graph. When `run_id` is given, wires a
    `FileSessionManager` keyed by it plus the `invocation_state`-persisting
    hook (design.md of `debate-durability`, Decisions 1-2) -- every node's
    return contract is unchanged either way; durability is added around the
    nodes, not through them. `run_id is None` (e.g. `GET /debate/stream`'s
    fresh, non-resumable run) builds a graph with no durability at all.

    `mock` (defaults to the `MOCK_LLM` config flag) swaps the six argument-turn
    nodes and the decision node for cached-transcript replay nodes (design.md
    of `mock-mode-eval-fixtures`, Decision 1). The moderator hub and the two
    audience-question responder nodes are never swapped -- the hub makes no
    LLM call, and the audience question is novel each run with no cached
    answer to replay, so a real `model` is still required even in mock mode."""
    if mock is None:
        mock = MOCK_LLM
    if model is None:
        model = _default_model()
    if memory_store is None:
        memory_store = default_memory_store()

    builder = GraphBuilder()

    hub = ModeratorHub(memory_store)
    audience = AudienceQuestionStub()

    if mock:
        decision = MockModeratorDecision()
        turn_nodes = {key: MockTurnNode(key, key) for key in MOCK_TURN_KEYS}
    else:
        decision = moderator_decision_node(model, memory_store)
        turn_nodes = {
            "pro_opening": pro_opening_node(model),
            "con_opening": con_opening_node(model),
            "pro_rebuttal": pro_rebuttal_node(model),
            "con_rebuttal": con_rebuttal_node(model),
            "pro_closing": pro_closing_node(model),
            "con_closing": con_closing_node(model),
        }

    nodes = [
        hub,
        turn_nodes["pro_opening"],
        turn_nodes["con_opening"],
        turn_nodes["pro_rebuttal"],
        turn_nodes["con_rebuttal"],
        audience,
        pro_addresses_question_node(model),
        con_addresses_question_node(model),
        turn_nodes["pro_closing"],
        turn_nodes["con_closing"],
        decision,
    ]
    for node in nodes:
        builder.add_node(node, node.id)

    builder.add_edge("moderator", "pro_opening", condition=_round("opening"))
    builder.add_edge("moderator", "pro_rebuttal", condition=_round("rebuttal"))
    builder.add_edge("moderator", "audience_question", condition=_round("audience"))
    builder.add_edge("moderator", "pro_closing", condition=_round("closing"))
    builder.add_edge("moderator", "moderator_decision", condition=_round("done"))

    builder.add_edge("pro_opening", "con_opening")
    builder.add_edge("con_opening", "moderator")
    builder.add_edge("pro_rebuttal", "con_rebuttal")
    builder.add_edge("con_rebuttal", "moderator")
    builder.add_edge("audience_question", "pro_addresses_question")
    builder.add_edge("pro_addresses_question", "con_addresses_question")
    builder.add_edge("con_addresses_question", "moderator")
    builder.add_edge("pro_closing", "con_closing")
    builder.add_edge("con_closing", "moderator")

    builder.set_entry_point("moderator")
    builder.set_max_node_executions(MAX_NODE_EXECUTIONS)

    hooks = [AudienceQuestionHook()]
    if run_id is not None:
        storage_dir = session_storage_dir if session_storage_dir is not None else SESSION_STORAGE_DIRECTORY
        # S3SessionManager when an AWS deployment target is configured,
        # FileSessionManager otherwise (deploy-to-agentcore design.md,
        # Decision 4). `InvocationStatePersistenceHook` is unchanged either
        # way -- its underlying save_invocation_state() call already branches
        # on the same config (src/core/session.py).
        if config.S3_SESSION_BUCKET:
            builder.set_session_manager(
                S3SessionManager(
                    session_id=run_id,
                    bucket=config.S3_SESSION_BUCKET,
                    prefix=config.S3_SESSION_PREFIX,
                    region_name=config.AWS_REGION,
                )
            )
        else:
            builder.set_session_manager(FileSessionManager(session_id=run_id, storage_dir=storage_dir))
        hooks.append(InvocationStatePersistenceHook(storage_dir, run_id))
    builder.set_hook_providers(hooks)

    return builder.build()
