"""T5 failover demo UI.

Talks to the debate-node cluster only through the nginx LB (`LB_URL`) for
starting/streaming debates — it never knows or cares which node actually
does the work, same as any real client. The one exception is the node
status row, which polls each node's `/debate/health` directly on its
published host port so a killed node visibly flips to down regardless of
what the LB is doing.

Layout is chat-app-style: a sidebar lists every debate started this session
(most recent first); the main panel renders the selected debate's transcript
as a sequence of moderator dividers, a "who's up next" pill, and speaker
turns — mirroring the graph's actual node sequence (see src/core/graph.py).

Streamlit reruns scripts on every interaction and on every timed refresh, so
anything that must survive a rerun (background SSE threads, accumulated
events, node health, debate history) lives in `st.session_state`, not in
module-level variables.
"""

import json
import queue
import threading
import time

import httpx
import streamlit as st
from concurrent.futures import ThreadPoolExecutor

LB_URL = "http://localhost:8080"
NODE_HEALTH_URLS = {
    "node-1": "http://localhost:8001/debate/health",
    "node-2": "http://localhost:8002/debate/health",
    "node-3": "http://localhost:8003/debate/health",
}
FAILURE_BANNER_SECONDS = 15
AUTO_REFRESH_SECONDS = 1.5
TYPEWRITER_DELAY_SECONDS = 0.03  # per-word delay when a turn's text is first revealed

# Mirrors the edges in src/core/graph.py: each round is Pro then Con, and a
# moderator_checkpoint event between them announces what's coming next.
# Third element is the state key holding the turn's text — matches the node
# name for every node except the two audience-question responders, whose
# node functions return `pro_audience_answer`/`con_audience_answer` instead.
SPEAKERS = {
    "pro_opening": ("pro", "Pro Opening", "pro_opening"),
    "con_opening": ("con", "Con Opening", "con_opening"),
    "pro_rebuttal": ("pro", "Pro Rebuttal", "pro_rebuttal"),
    "con_rebuttal": ("con", "Con Rebuttal", "con_rebuttal"),
    "pro_addresses_question": ("pro", "Pro Answers the Audience", "pro_audience_answer"),
    "con_addresses_question": ("con", "Con Answers the Audience", "con_audience_answer"),
    "pro_closing": ("pro", "Pro Closing", "pro_closing"),
    "con_closing": ("con", "Con Closing", "con_closing"),
}
ROUND_DIVIDER = {
    "rebuttal": "Moderator initiated Rebuttal Round",
    "closing": "Moderator initiated Closing Round",
    "decision": "Moderator's Conclusion",
}
ROLE_STYLE = {
    "pro": {"color": "#7c3aed", "label": "PRO"},
    "con": {"color": "#dc2626", "label": "CON"},
    "mod": {"color": "#2563eb", "label": "MOD"},
    "audience": {"color": "#059669", "label": "❓"},
}

st.set_page_config(page_title="Debate Bot — Failover Demo", page_icon="🗣️", layout="wide")


def init_state() -> None:
    defaults = {
        "debates": {},          # run_id -> {topic, started_at, events, event_queue, done}
        "debate_order": [],     # run_id insertion order, oldest first
        "active_run_id": None,
        "draft_topic": "Pro athletes are overpaid",
        "node_alive": {node: True for node in NODE_HEALTH_URLS},
        "failure_banner_until": 0.0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def relative_time(started_at: float) -> str:
    delta = time.time() - started_at
    if delta < 60:
        return "Just now"
    if delta < 3600:
        mins = int(delta // 60)
        return f"{mins} min ago"
    if delta < 86400:
        hrs = int(delta // 3600)
        return f"{hrs} hr ago" if hrs == 1 else f"{hrs} hrs ago"
    days = int(delta // 86400)
    return "1 day ago" if days == 1 else f"{days} days ago"


def poll_node_health() -> None:
    """Hit every node's /debate/health directly (never through the LB) so the
    status row reflects reality even for a node the LB has already stopped
    routing to."""

    def check(url: str) -> bool:
        try:
            return httpx.get(url, timeout=1.5).status_code == 200
        except httpx.HTTPError:
            return False

    with ThreadPoolExecutor(max_workers=len(NODE_HEALTH_URLS)) as pool:
        results = dict(zip(NODE_HEALTH_URLS, pool.map(check, NODE_HEALTH_URLS.values())))

    for node, alive in results.items():
        if st.session_state.node_alive.get(node, True) and not alive:
            st.session_state.failure_banner_until = time.time() + FAILURE_BANNER_SECONDS
        st.session_state.node_alive[node] = alive


STREAM_READ_TIMEOUT_SECONDS = 10.0  # comfortably above the relay's keepalive cadence (see RELAY_OWNERSHIP_POLL_SECONDS)
STREAM_RECONNECT_DELAY_SECONDS = 1.0
MAX_STREAM_RECONNECT_ATTEMPTS = 15


def consume_stream(run_id: str, event_q: "queue.Queue") -> None:
    """Runs in a background thread — one per debate, for its whole lifetime.
    Never touches st.session_state directly; the main thread drains event_q
    on each rerun instead.

    Reconnects automatically on a dropped or gone-quiet connection (e.g. the
    node serving this SSE stream itself died) rather than giving up — a fresh
    GET to /debate/stream/{run_id} lands on whichever node the LB picks next,
    which re-evaluates ownership and claims + resumes if needed. The server
    side (debates.py's debate_stream_relay) also self-heals a stale owner
    without a reconnect when it's just relaying, so this is a safety net for
    the case where the relaying node itself is the one that goes down.
    """
    url = f"{LB_URL}/debate/stream/{run_id}"
    timeout = httpx.Timeout(connect=10.0, read=STREAM_READ_TIMEOUT_SECONDS, write=10.0, pool=10.0)

    for attempt in range(MAX_STREAM_RECONNECT_ATTEMPTS):
        try:
            with httpx.stream("GET", url, timeout=timeout) as resp:
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[len("data:"):].strip())
                    except json.JSONDecodeError:
                        continue
                    event_q.put(event)
                    if event.get("node") in ("COMPLETE", "ERROR"):
                        event_q.put({"node": "_STREAM_CLOSED"})
                        return
        except httpx.HTTPError:
            pass  # dropped/timed-out connection — reconnect below rather than giving up
        time.sleep(STREAM_RECONNECT_DELAY_SECONDS)

    event_q.put({"node": "ERROR", "error": "stream reconnect attempts exhausted"})
    event_q.put({"node": "_STREAM_CLOSED"})


def start_debate(topic: str) -> None:
    resp = httpx.post(f"{LB_URL}/debate/start", json={"topic": topic}, timeout=10.0)
    resp.raise_for_status()
    run_id = resp.json()["run_id"]

    event_q = queue.Queue()
    st.session_state.debates[run_id] = {
        "topic": topic,
        "started_at": time.time(),
        "events": [],
        "event_queue": event_q,
        "done": False,
        "question_submitted": False,
    }
    st.session_state.debate_order.append(run_id)
    st.session_state.active_run_id = run_id

    threading.Thread(target=consume_stream, args=(run_id, event_q), daemon=True).start()


def submit_audience_question(run_id: str, question: str) -> None:
    """POST the audience's question for a paused debate — any node behind the
    LB can claim and resume it; the resulting events reach this same SSE
    connection via Redis pub/sub regardless of which node claims it."""
    resp = httpx.post(
        f"{LB_URL}/debate/{run_id}/audience-question",
        json={"question": question},
        timeout=10.0,
    )
    resp.raise_for_status()


def drain_all_queues() -> None:
    """Every debate's background thread keeps running (and its history keeps
    accumulating) regardless of which one is currently displayed — same as a
    real chat app keeps other conversations alive in the background."""
    for debate in st.session_state.debates.values():
        q = debate["event_queue"]
        while not q.empty():
            event = q.get_nowait()
            if event.get("node") == "_STREAM_CLOSED":
                debate["done"] = True
            else:
                debate["events"].append(event)


def render_divider(text: str) -> None:
    st.markdown(
        "<div style='display:flex;align-items:center;gap:12px;margin:1.1em 0;"
        "color:#888;font-size:0.85em;'>"
        "<div style='flex:1;border-top:1px dashed #555;'></div>"
        f"<div>{text}</div>"
        "<div style='flex:1;border-top:1px dashed #555;'></div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_speaker_pill(role: str, label: str) -> None:
    color = ROLE_STYLE[role]["color"]
    st.markdown(
        "<div style='text-align:center;margin:0.3em 0 1em;'>"
        f"<span style='background:{color};color:white;padding:4px 16px;"
        "border-radius:14px;font-size:0.8em;'>"
        f"● {label} is debating</span></div>",
        unsafe_allow_html=True,
    )


def _typewriter(text: str, delay: float = TYPEWRITER_DELAY_SECONDS):
    """Word-by-word generator for st.write_stream's built-in typewriter effect."""
    words = text.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(delay)


def render_message(role: str, text: str, node_id: str | None, animate: bool) -> None:
    style = ROLE_STYLE[role]
    cols = st.columns([1, 14], vertical_alignment="top")
    with cols[0]:
        st.markdown(
            f"<div style='width:34px;height:34px;border-radius:50%;background:{style['color']};"
            "color:white;display:flex;align-items:center;justify-content:center;"
            "font-size:0.65em;font-weight:700;'>"
            f"{style['label']}</div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        if animate and text:
            st.write_stream(_typewriter(text))
        else:
            st.write(text)
        if node_id:
            st.caption(f"served by `{node_id}`")


def render_audience_question_form(run_id: str, debate: dict) -> None:
    """Rendered only while the debate is sitting on the audience-question
    pause (the last event received is still AWAITING_AUDIENCE_QUESTION) and
    this browser session hasn't already submitted one — the spec allows
    exactly one question per debate, and the resume events take a moment to
    arrive over SSE after submitting, so a local flag prevents a double POST
    from a rerun in that gap."""
    if debate.get("question_submitted"):
        st.info("⏳ Waiting for the debate to resume with your question...")
        return

    with st.form(key=f"audience_question_form_{run_id}"):
        question = st.text_input("Ask a question for both debaters to address")
        submitted = st.form_submit_button("Submit Question")
    if submitted and question.strip():
        try:
            submit_audience_question(run_id, question.strip())
            debate["question_submitted"] = True
            st.rerun()
        except httpx.HTTPError as e:
            st.error(f"Failed to submit question: {e}")


def render_transcript(run_id: str, debate: dict) -> None:
    events = debate["events"]
    done = debate["done"]

    for event in events:
        node = event.get("node")
        state = event.get("state") or {}
        node_id = event.get("node_id")
        # Only animate a turn the first time it's rendered — every 1.5s poll
        # tick re-renders the whole transcript, and re-typewriting history on
        # every tick would be slow and keep replaying old turns.
        animate = not event.get("_shown")

        if node == "RUN_START":
            continue
        elif node == "RUN_RESUME":
            render_divider(f"Resumed on {node_id or 'a surviving node'}")
        elif node == "moderator_open":
            render_divider("Moderator initiated the debate")
        elif node == "moderator_checkpoint":
            render_divider(ROUND_DIVIDER.get(state.get("round"), "Moderator checkpoint"))
        elif node in SPEAKERS:
            role, label, state_key = SPEAKERS[node]
            render_divider(label)
            render_message(role, state.get(state_key, ""), node_id, animate)
            event["_shown"] = True
        elif node == "AWAITING_AUDIENCE_QUESTION":
            render_divider("Moderator invites an audience question")
        elif node == "audience_question":
            # Resuming re-runs this node (LangGraph re-executes a node from
            # its start on resume) - this time interrupt() returns the
            # submitted answer immediately instead of pausing again, so the
            # question now shows up as a normal completed-node update.
            question_text = state.get("audience_question", "")
            if question_text:
                render_divider("Audience Question")
                render_message("audience", question_text, node_id, animate)
                event["_shown"] = True
        elif node == "AWAITING_AUDIENCE_QUESTION_UNSUPPORTED":
            st.error(f"⚠️ {event.get('detail', 'This debate paused and cannot resume here.')}")
        elif node == "moderator_decision":
            render_message("mod", state.get("moderator_summary", ""), node_id, animate)
            event["_shown"] = True
            if state.get("winner"):
                st.success(f"🏆 Winner: {state['winner']}")
        elif node == "ERROR":
            st.error(f"⚠️ {event.get('error', 'unknown error')}")

    if not done and events:
        last_node = events[-1].get("node")
        last_round = (events[-1].get("state") or {}).get("round")
        if last_node == "AWAITING_AUDIENCE_QUESTION":
            render_audience_question_form(run_id, debate)
        elif last_node == "audience_question":
            render_speaker_pill("pro", "Pro")
        elif last_node in ("moderator_open",) or (last_node == "moderator_checkpoint" and last_round != "decision"):
            render_speaker_pill("pro", "Pro")
        elif last_node in ("pro_opening", "pro_rebuttal", "pro_addresses_question", "pro_closing"):
            render_speaker_pill("con", "Con")
        elif last_node == "moderator_checkpoint" and last_round == "decision":
            render_speaker_pill("mod", "Moderator")


def render_node_status() -> None:
    alive = st.session_state.node_alive
    up = sum(1 for ok in alive.values() if ok)
    total = len(alive)
    if up == total:
        st.success(f"✓ All nodes are up ({up}/{total})")
    else:
        detail = "  ".join(f"{node} {'✅' if ok else '❌'}" for node, ok in alive.items())
        st.error(detail)

    if time.time() < st.session_state.failure_banner_until:
        st.warning("⚠️ Node failure detected — resuming on another node...")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 🗨️ Debate Bot")
        st.caption("Multi-Node Failover")

        if st.button("➕ New Debate", use_container_width=True):
            st.session_state.active_run_id = None

        st.markdown("#### Debate Topics")
        if not st.session_state.debate_order:
            st.caption("No debates yet — start one below.")
        for run_id in reversed(st.session_state.debate_order):
            debate = st.session_state.debates[run_id]
            is_active = run_id == st.session_state.active_run_id
            title = debate["topic"][:40] + ("…" if len(debate["topic"]) > 40 else "")
            label = f"{'🟢 ' if is_active else '💬 '}{title}"
            if st.button(label, key=f"topic_{run_id}", use_container_width=True):
                st.session_state.active_run_id = run_id
            st.caption(relative_time(debate["started_at"]))


def live_panel() -> None:
    """Everything that needs to auto-refresh: sidebar history, node status,
    and the active transcript.

    Uses the classic `time.sleep` + `st.rerun()` polling pattern rather than
    `st.fragment(run_every=...)` — the latter depends on a browser-side JS
    timer pinging the server, which isn't reliably observable or testable
    (a headless run never ticks it), so a stalled fragment fails silently:
    the page just stops updating with no error shown. A full-script rerun
    loop is less smooth (brief flicker) but deterministic."""
    drain_all_queues()
    poll_node_health()
    render_sidebar()

    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            topic = st.text_input("Debate topic", value=st.session_state.draft_topic, label_visibility="visible")
            st.session_state.draft_topic = topic
        with right:
            st.write("")
            st.write("")
            if st.button("Start New Debate", type="primary", use_container_width=True):
                if topic.strip():
                    start_debate(topic.strip())
    render_node_status()

    active_id = st.session_state.active_run_id
    if active_id and active_id in st.session_state.debates:
        debate = st.session_state.debates[active_id]
        st.caption(f"Run ID: `{active_id}`")
        render_transcript(active_id, debate)
    elif st.session_state.debates:
        st.info("Select a debate from the sidebar, or start a new one above.")


def main() -> None:
    init_state()
    st.title("🗣️ Debate Bot — Multi-Node Failover Demo")
    st.caption(f"Load balancer: {LB_URL}")
    live_panel()

    time.sleep(AUTO_REFRESH_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
