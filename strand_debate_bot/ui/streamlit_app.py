"""Demo UI for the Strands debate graph.

Talks to this project's single FastAPI process (`API_BASE_URL`, no load
balancer, no node identity) via the async start/stream/submit-question API.
Layout is chat-app-style: a sidebar lists every debate started this session
(most recent first); the main panel renders the active debate's transcript as
moderator round dividers, a "who's up next" pill, and speaker turns -- keyed
off this graph's actual node ids (see src/core/graph.py), not the old
LangGraph-based system's.

The audience-question pause is two separate SSE connections, not one: the
server closes the stream exactly when it emits AWAITING_AUDIENCE_QUESTION,
and submitting the question opens a fresh GET against the same run_id to
receive the rest of the run (see debate_service.py's per-drive-call event
queue). Each debate's background thread reflects that: it exits normally at
the pause and a second thread is started only after a successful submission.

Streamlit reruns the whole script on every interaction and on every timed
refresh, so anything that must survive a rerun (background stream threads,
accumulated events, debate history) lives in `st.session_state`, not in
module-level variables.
"""

import json
import os
import queue
import threading
import time

import httpx
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
AUTO_REFRESH_SECONDS = 1.5
TYPEWRITER_DELAY_SECONDS = 0.03  # per-word delay when a turn's text is first revealed

# Mirrors the edges in src/core/graph.py: each round is Pro then Con. The
# third element is the invocation_state key holding the turn's text --
# matches the node name for every node except the two audience-question
# responders, whose node functions write into pro_audience_answer /
# con_audience_answer instead.
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

# The moderator is a single hub node, revisited once per round; its own
# completion event carries the round it just advanced to in state["round"]
# (src/core/state.py's ROUND_TRANSITIONS), which is what picks the divider.
MODERATOR_ROUND_DIVIDER = {
    "opening": "Moderator initiated the debate",
    "rebuttal": "Moderator initiated Rebuttal Round",
    "audience": "Moderator initiated the Audience Question Round",
    "closing": "Moderator initiated Closing Round",
    "done": "Moderator is deliberating",
}

ROLE_STYLE = {
    "pro": {"color": "#7c3aed", "label": "PRO"},
    "con": {"color": "#dc2626", "label": "CON"},
    "mod": {"color": "#2563eb", "label": "MOD"},
    "audience": {"color": "#059669", "label": "❓"},
}

st.set_page_config(page_title="Debate Bot", page_icon="🗣️", layout="wide")


def init_state() -> None:
    defaults = {
        "debates": {},  # run_id -> {topic, started_at, events, event_queue, question_submitted}
        "debate_order": [],  # run_id insertion order, oldest first
        "active_run_id": None,
        "draft_topic": "AI will replace software engineers",
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


def consume_stream(run_id: str, event_q: "queue.Queue") -> None:
    """Runs in a background thread for one segment of a debate's stream --
    from a fresh start, or from a resume after the audience-question pause.
    Never touches st.session_state directly; the main thread drains event_q
    on each rerun instead.

    Exits normally (pushing a _STREAM_CLOSED sentinel) whenever the server
    closes the connection -- which happens exactly at AWAITING_AUDIENCE_QUESTION
    or at COMPLETE/ERROR (see debate_service.py's _drive/_translate_event).
    There is no multi-node cluster to reconnect across here, so a genuine
    transport failure is reported as an ERROR event rather than retried.
    """
    url = f"{API_BASE_URL}/debate/stream/{run_id}"
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

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
    except httpx.HTTPError as exc:
        event_q.put({"node": "ERROR", "error": f"stream connection failed: {exc}"})
    finally:
        event_q.put({"node": "_STREAM_CLOSED"})


def start_debate(topic: str) -> None:
    resp = httpx.post(f"{API_BASE_URL}/debate/start", json={"topic": topic}, timeout=10.0)
    resp.raise_for_status()
    run_id = resp.json()["run_id"]

    event_q = queue.Queue()
    st.session_state.debates[run_id] = {
        "topic": topic,
        "started_at": time.time(),
        "events": [],
        "event_queue": event_q,
        "question_submitted": False,
    }
    st.session_state.debate_order.append(run_id)
    st.session_state.active_run_id = run_id

    threading.Thread(target=consume_stream, args=(run_id, event_q), daemon=True).start()


def submit_audience_question(run_id: str, question: str) -> None:
    """POSTs the audience's question, then opens a fresh stream segment --
    the server's event queue for this run was replaced server-side on
    submission (DebateService.submit_audience_question), so the previous
    stream thread's connection (already closed) cannot see the rest of the
    run; a new GET against the same run_id is required."""
    resp = httpx.post(
        f"{API_BASE_URL}/debate/{run_id}/audience-question",
        json={"question": question},
        timeout=10.0,
    )
    resp.raise_for_status()

    debate = st.session_state.debates[run_id]
    new_event_q = queue.Queue()
    debate["event_queue"] = new_event_q
    threading.Thread(target=consume_stream, args=(run_id, new_event_q), daemon=True).start()


def drain_all_queues() -> None:
    """Every debate's background thread keeps running (and its history keeps
    accumulating) regardless of which one is currently displayed -- same as a
    real chat app keeps other conversations alive in the background."""
    for debate in st.session_state.debates.values():
        q = debate["event_queue"]
        while not q.empty():
            event = q.get_nowait()
            if event.get("node") != "_STREAM_CLOSED":
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
    """Word-by-word generator for st.write_stream's built-in typewriter
    effect. The backend only emits whole-turn-complete events (no
    token-level streaming -- see design.md), so this is a simulated reveal
    over already-finished text, not a reflection of live generation."""
    words = text.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        time.sleep(delay)


def render_message(role: str, text: str, animate: bool) -> None:
    """No node/server identity is rendered here by design -- this backend's
    events never carry one, and the UI never should (spec.md, "No
    multi-node or failover presentation")."""
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


def render_audience_question_form(run_id: str, debate: dict) -> None:
    """Rendered only while the debate is sitting on the audience-question
    pause (the last received event is still AWAITING_AUDIENCE_QUESTION) and
    this browser session hasn't already submitted one -- the API allows
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

    for event in events:
        node = event.get("node")
        state = event.get("state") or {}
        # Only animate a turn the first time it's rendered -- every poll tick
        # re-renders the whole transcript, and re-typewriting history on
        # every tick would be slow and keep replaying old turns.
        animate = not event.get("_shown")

        if node == "moderator":
            render_divider(MODERATOR_ROUND_DIVIDER.get(state.get("round"), "Moderator checkpoint"))
        elif node in SPEAKERS:
            role, label, state_key = SPEAKERS[node]
            render_divider(label)
            render_message(role, state.get(state_key, ""), animate)
            event["_shown"] = True
        elif node == "AWAITING_AUDIENCE_QUESTION":
            render_divider("Moderator invites an audience question")
        elif node == "audience_question":
            question_text = state.get("audience_question", "")
            if question_text:
                render_divider("Audience Question")
                render_message("audience", question_text, animate)
                event["_shown"] = True
        elif node == "AWAITING_AUDIENCE_QUESTION_UNSUPPORTED":
            st.error(f"⚠️ {event.get('detail', 'This debate paused and cannot resume here.')}")
        elif node == "moderator_decision":
            render_divider("Moderator's Conclusion")
            render_message("mod", state.get("justification", ""), animate)
            event["_shown"] = True
            if state.get("winner"):
                st.success(f"🏆 Winner: {state['winner']}")
        elif node == "ERROR":
            st.error(f"⚠️ {event.get('error', 'unknown error')}")

    if not events:
        return

    last_event = events[-1]
    last_node = last_event.get("node")
    last_round = (last_event.get("state") or {}).get("round")

    if last_node == "AWAITING_AUDIENCE_QUESTION":
        render_audience_question_form(run_id, debate)
    elif last_node == "audience_question":
        render_speaker_pill("pro", "Pro")
    elif last_node == "moderator":
        render_speaker_pill("mod", "Moderator") if last_round == "done" else render_speaker_pill("pro", "Pro")
    elif last_node in ("pro_opening", "pro_rebuttal", "pro_addresses_question", "pro_closing"):
        render_speaker_pill("con", "Con")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 🗨️ Debate Bot")
        st.caption("Live Demo")

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
    """Everything that needs to auto-refresh: sidebar history and the active
    transcript.

    Uses the classic `time.sleep` + `st.rerun()` polling pattern rather than
    `st.fragment(run_every=...)` -- the latter depends on a browser-side JS
    timer pinging the server, which isn't reliably observable or testable
    (a headless run never ticks it), so a stalled fragment fails silently:
    the page just stops updating with no error shown. A full-script rerun
    loop is less smooth (brief flicker) but deterministic."""
    drain_all_queues()
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

    active_id = st.session_state.active_run_id
    if active_id and active_id in st.session_state.debates:
        debate = st.session_state.debates[active_id]
        st.caption(f"Run ID: `{active_id}`")
        render_transcript(active_id, debate)
    elif st.session_state.debates:
        st.info("Select a debate from the sidebar, or start a new one above.")


def main() -> None:
    init_state()
    st.title("🗣️ Debate Bot")
    st.caption(f"API: {API_BASE_URL}")
    live_panel()

    time.sleep(AUTO_REFRESH_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
