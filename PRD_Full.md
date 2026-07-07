# PRD: Real-Time Multi-Agent Debate Chatbot with Memory

## Context
The goal is to build a multi-agent chatbot that conducts structured, real-time debates. Three agents (Moderator, Pro, Con) collaborate through defined rounds, stream output live, and use vector memory to evolve argument quality across debates. This PRD breaks that system into Epics and Stories for implementation.

---

## Epic 1: Agent Architecture & Core Framework

Set up the foundational multi-agent system with Moderator, Pro, and Con agents.

| Story ID | Description | Why | Acceptance Criteria | Priority | Effort |
|----------|-------------|-----|---------------------|----------|--------|
| S_1.1 | As a system, initialize a Moderator agent that orchestrates debate flow | So that all agents have a single controller managing turns, timing, and state transitions | Moderator can start/stop a debate, assign turns, and track round state | High | M |
| S_1.2 | As a system, initialize a Pro agent that receives a topic and generates arguments in favor | So that the debate has a structured affirmative voice | Pro agent generates ≥200-word opening, ≥100-word rebuttal, 50–100-word closing | High | M |
| S_1.3 | As a system, initialize a Con agent that receives a topic and generates counter-arguments | So that the debate has a structured opposing voice | Con agent generates ≥200-word opening, ≥100-word rebuttal, 50–100-word closing | High | M |
| S_1.4 | As a developer, define a shared message/state schema for inter-agent communication | So that agents can read each other's arguments and respond coherently | All agents produce and consume a common structured message format | High | S |
| S_1.5 | As a developer, wire agents through a LangGraph or equivalent orchestration graph | So that the debate flow is deterministic and testable | Graph edges enforce correct turn order; unit tests pass for each transition | High | L |

---

## Epic 2: Structured Debate Flow

Implement the four-round debate structure enforced by the Moderator.

| Story ID | Description | Why | Acceptance Criteria | Priority | Effort |
|----------|-------------|-----|---------------------|----------|--------|
| S_2.1 | As a user, trigger an Opening Round where Pro then Con each present ~200-word arguments | So that both sides establish their core position before rebuttals | Opening round completes in correct order; word counts within ±20% of target | High | M |
| S_2.2 | As a user, trigger a Rebuttal Round where each agent directly counters the other's opening | So that the debate is interactive, not just parallel monologues | Each rebuttal explicitly references at least one point from the opposing opening | High | M |
| S_2.3 | As a user, trigger Closing Remarks where each agent summarizes their strongest points | So that the debate concludes clearly before the Moderator judges | Closing remarks are 50–100 words and do not introduce new arguments | Medium | S |
| S_2.4 | As a Moderator, evaluate both sides and declare a winner with justification | So that every debate has a definitive outcome | Moderator output includes summary of each side and a justified winner declaration | High | M |
| S_2.5 | As a developer, enforce round sequencing so no agent speaks out of turn | So that the debate structure is reliable and predictable | Integration test confirms rounds always execute in order: Opening → Rebuttal → Closing → Decision | High | S |

---

## Epic 3: Real-Time Streaming

Stream debate output step-by-step to simulate a live, conversational experience.

| Story ID | Description | Why | Acceptance Criteria | Priority | Effort |
|----------|-------------|-----|---------------------|----------|--------|
| S_3.1 | As a user, see status announcements before each agent speaks (e.g., "Pro Agent is presenting opening arguments…") | So that the debate feels live and the user always knows what is happening | Status line appears before each agent turn with correct agent name and round label | High | S |
| S_3.2 | As a user, see each agent's response streamed token-by-token rather than appearing all at once | So that reading the debate feels like watching it unfold in real time | LLM streaming is enabled; tokens appear progressively with no full-text delay | High | M |
| S_3.3 | As a developer, expose a streaming API endpoint or CLI entrypoint that accepts a topic and yields events | So that clients (UI or terminal) can consume the debate stream | Endpoint returns server-sent events or async generator; topic param is required | High | M |
| S_3.4 | As a user, see a clear visual separator or label between each agent's turn in the output | So that it is easy to follow who said what | Each turn is preceded by an agent label and followed by a blank line or divider | Medium | S |

---

## Epic 4: Vector Memory Integration

Store and retrieve past debates using a vector database to improve argument quality over time.

| Story ID | Description | Why | Acceptance Criteria | Priority | Effort |
|----------|-------------|-----|---------------------|----------|--------|
| S_4.1 | As a system, persist each completed debate (topic, pro arguments, con arguments, outcome) to a vector store | So that future debates can learn from past ones | After a debate, a record is upserted into the vector DB with all required fields | High | M |
| S_4.2 | As an agent, retrieve semantically similar past debates before generating each argument | So that agents avoid repeating identical points and can build on prior reasoning | Retrieval query runs against vector DB; top-k results are injected into agent context | High | L |
| S_4.3 | As a Moderator, decide when retrieved memory is relevant before passing it to agents | So that memory enhances quality without polluting unrelated debates with noise | Moderator applies a relevance threshold; irrelevant retrievals are filtered out | Medium | M |
| S_4.4 | As a system, embed debate content using a consistent embedding model (e.g., text-embedding-3-small) | So that semantic search is accurate and reproducible | Embedding model is configurable via env var; all records use the same model version | High | S |
| S_4.5 | As a developer, provide a local vector store option (e.g., ChromaDB) for development and a production option (e.g., Pinecone/Weaviate) | So that the system can be developed without cloud dependencies and scaled when needed | DB backend is abstracted behind an interface; switching requires only a config change | Medium | L |

---

## Epic 5: Topic Intake & User Interface

Accept a debate topic from the user and present the debate output clearly.

| Story ID | Description | Why | Acceptance Criteria | Priority | Effort |
|----------|-------------|-----|---------------------|----------|--------|
| S_5.1 | As a user, enter a free-text debate topic to start a new debate | So that the system works on any topic without code changes | Topic is accepted via CLI arg or API request body; empty input is rejected with a helpful message | High | S |
| S_5.2 | As a user, see the full debate transcript after the stream completes | So that I can review the entire debate in one place | Transcript is printed/returned at the end with all turns labeled | Medium | S |
| S_5.3 | As a user, see the winner declaration prominently at the end of the debate | So that the outcome is immediately clear | Winner section is visually distinct (e.g., bold label or separator) in the output | Medium | S |

---

## Epic 6: Observability & Developer Experience

Make the system easy to run, debug, and extend.

| Story ID | Description | Why | Acceptance Criteria | Priority | Effort |
|----------|-------------|-----|---------------------|----------|--------|
| S_6.1 | As a developer, run the full debate system with a single command | So that onboarding and demos require minimal setup | README documents `pip install -r requirements.txt && python main.py --topic "..."` | High | S |
| S_6.2 | As a developer, configure LLM provider, model, and vector DB via environment variables | So that credentials and model choices are not hardcoded | `.env.example` lists all required vars; app fails fast with a clear error if any are missing | High | S |
| S_6.3 | As a developer, view structured logs showing which agent is active and what memory was retrieved | So that the internal flow is debuggable without reading source code | Log lines include timestamp, agent name, round, and memory retrieval count | Medium | M |
| S_6.4 | As a developer, run unit tests for agent logic and integration tests for the debate flow | So that regressions are caught before they reach production | `pytest` suite covers: round ordering, word-count enforcement, memory read/write, streaming events | Medium | L |

---

## Story Effort Key
- **S** = Small (< 1 day)
- **M** = Medium (1–2 days)
- **L** = Large (3–5 days)
