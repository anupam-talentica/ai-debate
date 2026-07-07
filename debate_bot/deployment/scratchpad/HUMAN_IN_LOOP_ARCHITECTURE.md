# Human-in-the-Loop Debate Bot Architecture

## Problem Statement

The current production guide assumes agent-only debates (runs to completion in one request). Adding a human participant requires:
1. **Bidirectional communication** (agent ↔ UI, not just agent → UI)
2. **Session state persistence** (debate may take hours across multiple user interactions)
3. **Turn-based state machine** (strict ordering: Pro opens → Con opens/responds → Pro rebuts → etc.)
4. **Graceful reconnection** (user closes browser, network drops, server restarts)

HTTP/REST streaming (SSE/long-polling) **cannot support this** because:
- **Connection timeout**: SSE has implicit 30–60s timeout. Human thinks for 5 minutes → connection dies.
- **No bidirectional flow**: Can't send human input while agent is waiting.
- **Idempotency doesn't help**: The debate state is temporal and path-dependent. You can't "retry" without knowing where you were.

---

## Solution: WebSocket + State Machine + Database

```
UI (React/Vue)
    ↓
WebSocket Server (FastAPI + Starlette)
    ↓
Session Manager (in-memory + database)
    ↓
Debate State Machine (who's turn? timeout?)
    ↓
LangGraph (agent nodes)
    ↓
Claude LLM
```

### 1. Database Schema

```python
# debate_bot/models.py
from datetime import datetime
from enum import Enum
from typing import Optional
import json
from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class DebatePhase(str, Enum):
    """Enum for debate phases to enforce strict ordering."""
    PRO_OPENING = "pro_opening"
    CON_OPENING = "con_opening"
    PRO_REBUTTAL = "pro_rebuttal"
    CON_REBUTTAL = "con_rebuttal"
    PRO_CLOSING = "pro_closing"
    CON_CLOSING = "con_closing"
    DECISION = "decision"
    COMPLETED = "completed"

class DebateSession(Base):
    """Persistent debate session — survives server restarts."""
    __tablename__ = "debate_sessions"

    id = Column(String(36), primary_key=True)  # UUID
    topic = Column(String(500), nullable=False)
    
    # Participants
    pro_participant = Column(String(50), nullable=False)  # "agent" or username
    con_participant = Column(String(50), nullable=False)  # "agent" or username
    
    # State machine
    current_phase = Column(SQLEnum(DebatePhase), nullable=False)
    phase_timeout_at = Column(DateTime, nullable=True)  # When current phase expires
    
    # Content (stored as JSON for flexibility)
    pro_opening = Column(Text, default="")
    con_opening = Column(Text, default="")
    pro_rebuttal = Column(Text, default="")
    con_rebuttal = Column(Text, default="")
    pro_closing = Column(Text, default="")
    con_closing = Column(Text, default="")
    moderator_summary = Column(Text, default="")
    winner = Column(String(50), default="")
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    def to_dict(self):
        """Serialize to JSON for WebSocket broadcast."""
        return {
            "id": self.id,
            "topic": self.topic,
            "pro_participant": self.pro_participant,
            "con_participant": self.con_participant,
            "current_phase": self.current_phase.value,
            "pro_opening": self.pro_opening,
            "con_opening": self.con_opening,
            "pro_rebuttal": self.pro_rebuttal,
            "con_rebuttal": self.con_rebuttal,
            "pro_closing": self.pro_closing,
            "con_closing": self.con_closing,
            "moderator_summary": self.moderator_summary,
            "winner": self.winner,
        }

class DebateMessage(Base):
    """Audit log: every action in the debate."""
    __tablename__ = "debate_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    actor = Column(String(50), nullable=False)  # "pro", "con", "moderator", "system"
    event_type = Column(String(50), nullable=False)  # "argument_submitted", "phase_timeout", "reconnected"
    content = Column(Text, nullable=True)
    metadata = Column(Text, nullable=True)  # JSON
```

### 2. Session Manager (In-Memory + Async)

```python
# debate_bot/session_manager.py
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import asyncio
from debate_bot.models import DebateSession, DebatePhase, DebateMessage

class DebateSessionManager:
    """
    Manages active debate sessions.
    - In-memory cache for fast access (active sessions)
    - Database persistence for durability (reconnection, replay)
    - Async task scheduling for timeouts
    """
    
    def __init__(self, db_session):
        self.db_session = db_session
        self.active_sessions: Dict[str, DebateSession] = {}  # session_id → DebateSession
        self.phase_timers: Dict[str, asyncio.Task] = {}      # session_id → timeout task
        self.subscribers: Dict[str, set] = {}                # session_id → set of WebSocket connections
        
        # Phase durations (in seconds)
        self.phase_durations = {
            DebatePhase.PRO_OPENING: 300,      # 5 min (agent: immediate, human: 5 min to respond)
            DebatePhase.CON_OPENING: 300,
            DebatePhase.PRO_REBUTTAL: 180,     # 3 min
            DebatePhase.CON_REBUTTAL: 180,
            DebatePhase.PRO_CLOSING: 120,      # 2 min
            DebatePhase.CON_CLOSING: 120,
            DebatePhase.DECISION: 60,          # 1 min (moderator decides)
        }

    async def create_debate(self, topic: str, pro: str, con: str) -> str:
        """Create a new debate session. Returns session_id."""
        session_id = str(uuid.uuid4())
        
        session = DebateSession(
            id=session_id,
            topic=topic,
            pro_participant=pro,
            con_participant=con,
            current_phase=DebatePhase.PRO_OPENING,
        )
        
        self.db_session.add(session)
        self.db_session.commit()
        
        self.active_sessions[session_id] = session
        self.subscribers[session_id] = set()
        
        # Start timeout for PRO_OPENING phase
        await self._schedule_phase_timeout(session_id)
        
        return session_id

    async def submit_argument(self, session_id: str, phase: DebatePhase, content: str) -> bool:
        """
        Submit an argument for the current phase.
        Returns True if accepted, False if not in the right phase.
        """
        session = self.active_sessions.get(session_id)
        if not session or session.current_phase != phase:
            return False
        
        # Map phase to session attribute
        phase_field = {
            DebatePhase.PRO_OPENING: "pro_opening",
            DebatePhase.CON_OPENING: "con_opening",
            DebatePhase.PRO_REBUTTAL: "pro_rebuttal",
            DebatePhase.CON_REBUTTAL: "con_rebuttal",
            DebatePhase.PRO_CLOSING: "pro_closing",
            DebatePhase.CON_CLOSING: "con_closing",
        }
        
        setattr(session, phase_field[phase], content)
        session.updated_at = datetime.utcnow()
        
        # Log the action
        msg = DebateMessage(
            session_id=session_id,
            actor="con" if "CON" in phase.value else "pro",
            event_type="argument_submitted",
            content=content,
        )
        self.db_session.add(msg)
        self.db_session.commit()
        
        # Cancel the timeout (argument received, move to next phase)
        await self._advance_phase(session_id)
        
        # Broadcast to all watchers
        await self._broadcast(session_id, {
            "event": "argument_submitted",
            "phase": phase.value,
            "content": content,
            "session": session.to_dict(),
        })
        
        return True

    async def _advance_phase(self, session_id: str) -> None:
        """Move to the next phase in the debate."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
        
        # Define phase transitions
        phase_order = [
            DebatePhase.PRO_OPENING,
            DebatePhase.CON_OPENING,
            DebatePhase.PRO_REBUTTAL,
            DebatePhase.CON_REBUTTAL,
            DebatePhase.PRO_CLOSING,
            DebatePhase.CON_CLOSING,
            DebatePhase.DECISION,
            DebatePhase.COMPLETED,
        ]
        
        current_idx = phase_order.index(session.current_phase)
        if current_idx < len(phase_order) - 1:
            session.current_phase = phase_order[current_idx + 1]
            session.updated_at = datetime.utcnow()
            self.db_session.commit()
            
            # Cancel old timeout
            if session_id in self.phase_timers:
                self.phase_timers[session_id].cancel()
            
            # Schedule new timeout (unless in COMPLETED state)
            if session.current_phase != DebatePhase.COMPLETED:
                await self._schedule_phase_timeout(session_id)
                
                # Broadcast phase change
                await self._broadcast(session_id, {
                    "event": "phase_changed",
                    "current_phase": session.current_phase.value,
                    "timeout_seconds": self.phase_durations.get(session.current_phase, 60),
                    "session": session.to_dict(),
                })

    async def _schedule_phase_timeout(self, session_id: str) -> None:
        """Schedule a timeout task for the current phase."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
        
        duration = self.phase_durations.get(session.current_phase, 60)
        session.phase_timeout_at = datetime.utcnow() + timedelta(seconds=duration)
        self.db_session.commit()
        
        async def timeout_handler():
            await asyncio.sleep(duration)
            await self._on_phase_timeout(session_id)
        
        # Cancel old timer if exists
        if session_id in self.phase_timers:
            self.phase_timers[session_id].cancel()
        
        self.phase_timers[session_id] = asyncio.create_task(timeout_handler())

    async def _on_phase_timeout(self, session_id: str) -> None:
        """Handle timeout when human doesn't respond in time."""
        session = self.active_sessions.get(session_id)
        if not session:
            return
        
        # Log timeout event
        msg = DebateMessage(
            session_id=session_id,
            actor="system",
            event_type="phase_timeout",
            metadata=json.dumps({"phase": session.current_phase.value}),
        )
        self.db_session.add(msg)
        self.db_session.commit()
        
        # Who timed out?
        is_pro_phase = "PRO" in session.current_phase.value
        timeout_participant = session.pro_participant if is_pro_phase else session.con_participant
        
        # If agent times out, that's a bug. If human times out, they forfeit.
        if timeout_participant == "agent":
            # Agent should respond immediately—log as error
            await self._broadcast(session_id, {
                "event": "error",
                "message": f"Agent did not respond in time for {session.current_phase.value}",
            })
        else:
            # Human forfeited their turn
            await self._broadcast(session_id, {
                "event": "phase_timeout",
                "participant": timeout_participant,
                "phase": session.current_phase.value,
                "message": f"{timeout_participant} did not respond in time. Their argument is forfeit.",
            })
            
            # Auto-advance to next phase
            await self._advance_phase(session_id)

    async def register_subscriber(self, session_id: str, websocket) -> None:
        """Register a WebSocket connection to receive updates."""
        if session_id not in self.subscribers:
            self.subscribers[session_id] = set()
        self.subscribers[session_id].add(websocket)

    async def unregister_subscriber(self, session_id: str, websocket) -> None:
        """Unregister a WebSocket connection."""
        if session_id in self.subscribers:
            self.subscribers[session_id].discard(websocket)

    async def _broadcast(self, session_id: str, message: dict) -> None:
        """Broadcast a message to all subscribers of a session."""
        if session_id not in self.subscribers:
            return
        
        message_json = json.dumps(message)
        for websocket in self.subscribers[session_id]:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                # WebSocket closed; unregister
                await self.unregister_subscriber(session_id, websocket)

    async def reconnect_session(self, session_id: str) -> Optional[DebateSession]:
        """
        Recover a session from database after disconnect.
        Returns the full session state for the reconnecting client.
        """
        session = self.db_session.query(DebateSession).filter_by(id=session_id).first()
        if session:
            self.active_sessions[session_id] = session
            
            # Log reconnection
            msg = DebateMessage(
                session_id=session_id,
                actor="system",
                event_type="reconnected",
            )
            self.db_session.add(msg)
            self.db_session.commit()
            
            # Re-schedule timeout if not completed
            if session.current_phase != DebatePhase.COMPLETED:
                await self._schedule_phase_timeout(session_id)
        
        return session
```

### 3. WebSocket Server Endpoint

```python
# debate_bot/server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
import json
import asyncio
from sqlalchemy.orm import Session
from debate_bot.session_manager import DebateSessionManager, DebatePhase
from debate_bot.models import DebateSession
from graph import build_graph
from app import run_debate

app = FastAPI(title="Human-in-the-Loop Debate Bot")
session_manager = None  # Initialized in startup

# Store graph instance
graph = build_graph()

@app.on_event("startup")
async def startup():
    global session_manager
    from database import SessionLocal
    db = SessionLocal()
    session_manager = DebateSessionManager(db)

@app.post("/debate/create")
async def create_debate(topic: str, pro: str = "agent", con: str = "agent"):
    """Create a new debate session. Pro/con can be 'agent' or a username."""
    db = SessionLocal()
    session_id = await session_manager.create_debate(topic, pro, con)
    return {"session_id": session_id, "topic": topic}

@app.websocket("/ws/debate/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for a debate session.
    Handles bidirectional communication: human arguments in, live updates out.
    """
    await websocket.accept()
    db = SessionLocal()
    
    # Recover session from database if it exists (reconnection case)
    session = await session_manager.reconnect_session(session_id)
    if not session:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return
    
    # Register this connection to receive broadcasts
    await session_manager.register_subscriber(session_id, websocket)
    
    # Send initial state
    await websocket.send_json({
        "event": "connected",
        "session": session.to_dict(),
        "current_phase": session.current_phase.value,
    })
    
    # If it's an agent's turn, invoke the agent
    await _invoke_agent_if_needed(session_id, session, db)
    
    try:
        while True:
            # Wait for human input or heartbeat
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "submit_argument":
                # Human submitting an argument
                phase = DebatePhase(message["phase"])
                content = message["content"]
                
                # Validate it's the right turn
                session = db.query(DebateSession).filter_by(id=session_id).first()
                if session.current_phase != phase:
                    await websocket.send_json({
                        "error": f"Not your turn. Current phase: {session.current_phase.value}"
                    })
                    continue
                
                # Submit the argument
                success = await session_manager.submit_argument(session_id, phase, content)
                if success:
                    session = db.query(DebateSession).filter_by(id=session_id).first()
                    
                    # If next phase is agent's turn, invoke agent
                    await _invoke_agent_if_needed(session_id, session, db)
            
            elif message.get("type") == "heartbeat":
                # Ping to keep connection alive
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        await session_manager.unregister_subscriber(session_id, websocket)
    except Exception as e:
        await websocket.send_json({"error": str(e)})
        await session_manager.unregister_subscriber(session_id, websocket)

async def _invoke_agent_if_needed(session_id: str, session: DebateSession, db: Session) -> None:
    """
    If the current phase's participant is an agent, invoke LangGraph and stream results.
    """
    is_pro_phase = "PRO" in session.current_phase.value
    participant = session.pro_participant if is_pro_phase else session.con_participant
    
    if participant != "agent":
        # It's a human's turn — don't invoke agent
        return
    
    # Stream agent's response via LangGraph
    try:
        # Build state dict for LangGraph
        state = {
            "topic": session.topic,
            "round": session.current_phase.value,
            "pro_opening": session.pro_opening,
            "con_opening": session.con_opening,
            "pro_rebuttal": session.pro_rebuttal,
            "con_rebuttal": session.con_rebuttal,
            "pro_closing": session.pro_closing,
            "con_closing": session.con_closing,
            "moderator_summary": session.moderator_summary,
            "winner": session.winner,
            "memory_context": [],
        }
        
        # Stream tokens as they arrive
        async for chunk in graph.astream(state):
            # Broadcast token stream to all watchers
            await session_manager._broadcast(session_id, {
                "event": "agent_streaming",
                "phase": session.current_phase.value,
                "chunk": chunk,
            })
        
        # After streaming completes, extract final argument and save to DB
        final_state = await graph.ainvoke(state)
        
        # Extract argument for this phase and save
        phase_field = {
            DebatePhase.PRO_OPENING: "pro_opening",
            DebatePhase.CON_OPENING: "con_opening",
            DebatePhase.PRO_REBUTTAL: "pro_rebuttal",
            DebatePhase.CON_REBUTTAL: "con_rebuttal",
            DebatePhase.PRO_CLOSING: "pro_closing",
            DebatePhase.CON_CLOSING: "con_closing",
            DebatePhase.DECISION: "moderator_summary",
        }.get(session.current_phase)
        
        if phase_field:
            setattr(session, phase_field, final_state.get(phase_field, ""))
            db.commit()
        
        # Broadcast argument complete and advance phase
        await session_manager._broadcast(session_id, {
            "event": "argument_complete",
            "phase": session.current_phase.value,
        })
        
        # Advance to next phase
        await session_manager._advance_phase(session_id)
        
        # If next phase is also an agent's turn, invoke again
        session = db.query(DebateSession).filter_by(id=session_id).first()
        await _invoke_agent_if_needed(session_id, session, db)
    
    except Exception as e:
        await session_manager._broadcast(session_id, {
            "event": "error",
            "message": f"Agent error: {str(e)}",
        })

@app.get("/debate/{session_id}")
async def get_debate_status(session_id: str):
    """GET debate state (for reconnecting clients or polling)."""
    db = SessionLocal()
    session = db.query(DebateSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

### 4. Frontend (React/Vue) — WebSocket Client

```javascript
// frontend/src/DebateSession.jsx
import React, { useState, useEffect, useRef } from 'react';

const DebateSession = ({ sessionId }) => {
  const [session, setSession] = useState(null);
  const [currentPhase, setCurrentPhase] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [userInput, setUserInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [phaseTimeoutAt, setPhaseTimeoutAt] = useState(null);
  const wsRef = useRef(null);
  const heartbeatRef = useRef(null);

  useEffect(() => {
    // Connect to WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsRef.current = new WebSocket(`${protocol}//${window.location.host}/ws/debate/${sessionId}`);

    wsRef.current.onopen = () => console.log("Connected to debate");

    wsRef.current.onmessage = (event) => {
      const message = JSON.parse(event.data);

      if (message.event === "connected" || message.event === "argument_complete") {
        // Update full session state
        setSession(message.session);
        setCurrentPhase(message.current_phase || message.session.current_phase);
        setPhaseTimeoutAt(message.timeout_seconds ? Date.now() + message.timeout_seconds * 1000 : null);
        setStreamingText(""); // Clear old streaming
        setUserInput("");
      }

      if (message.event === "agent_streaming") {
        // Append tokens from agent as they arrive
        setStreamingText((prev) => prev + message.chunk);
      }

      if (message.event === "phase_changed") {
        setCurrentPhase(message.current_phase);
        setPhaseTimeoutAt(Date.now() + message.timeout_seconds * 1000);
        setStreamingText("");
      }

      if (message.event === "phase_timeout") {
        alert(`${message.participant} did not respond in time.`);
      }

      if (message.event === "error") {
        console.error("Debate error:", message.message);
      }
    };

    wsRef.current.onerror = (error) => console.error("WebSocket error:", error);
    wsRef.current.onclose = () => console.log("Disconnected from debate");

    // Send heartbeat every 25 seconds to keep connection alive
    heartbeatRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "heartbeat" }));
      }
    }, 25000);

    return () => {
      clearInterval(heartbeatRef.current);
      wsRef.current?.close();
    };
  }, [sessionId]);

  const handleSubmit = async () => {
    if (!userInput.trim()) return;

    setIsSubmitting(true);
    wsRef.current.send(
      JSON.stringify({
        type: "submit_argument",
        phase: currentPhase,
        content: userInput,
      })
    );
    setIsSubmitting(false);
  };

  if (!session) return <div>Loading debate...</div>;

  const isMyTurn = 
    (currentPhase.includes("PRO") && session.pro_participant !== "agent") ||
    (currentPhase.includes("CON") && session.con_participant !== "agent");

  const isAgentTurn = 
    (currentPhase.includes("PRO") && session.pro_participant === "agent") ||
    (currentPhase.includes("CON") && session.con_participant === "agent");

  return (
    <div style={{ maxWidth: "800px", margin: "0 auto", padding: "20px" }}>
      <h1>Debate: {session.topic}</h1>
      <p>Phase: <strong>{currentPhase}</strong></p>
      {phaseTimeoutAt && (
        <p>Time remaining: <Timer until={phaseTimeoutAt} /></p>
      )}

      <div style={{ marginTop: "30px", padding: "15px", border: "1px solid #ccc" }}>
        {isAgentTurn ? (
          <div>
            <p><em>Agent is responding...</em></p>
            <div style={{ minHeight: "100px", whiteSpace: "pre-wrap" }}>
              {streamingText}
            </div>
          </div>
        ) : isMyTurn ? (
          <div>
            <p>It's your turn to respond:</p>
            <textarea
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              style={{ width: "100%", height: "200px", padding: "10px" }}
              placeholder="Enter your argument..."
            />
            <button onClick={handleSubmit} disabled={isSubmitting}>
              Submit Argument
            </button>
          </div>
        ) : (
          <div>
            <p><em>Waiting for {session.pro_participant === "agent" ? "agent" : "human"} to respond...</em></p>
          </div>
        )}
      </div>

      <div style={{ marginTop: "20px", fontSize: "12px", color: "#666" }}>
        <p><strong>Pro ({session.pro_participant}):</strong> {session.pro_opening || "(not started)"}</p>
        <p><strong>Con ({session.con_participant}):</strong> {session.con_opening || "(not started)"}</p>
      </div>
    </div>
  );
};

const Timer = ({ until }) => {
  const [remaining, setRemaining] = useState(Math.max(0, (until - Date.now()) / 1000));

  useEffect(() => {
    const interval = setInterval(() => {
      setRemaining((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return <span>{Math.floor(remaining)}s</span>;
};

export default DebateSession;
```

---

## Key Design Decisions

### 1. **WebSocket Over HTTP**
- **Why**: Allows true bidirectional communication + server-initiated broadcasts
- **Heartbeat**: Send every 25s to prevent proxy/firewall timeouts
- **Reconnection**: Store `session_id` in localStorage; on reconnect, query `/debate/{session_id}` to recover state

### 2. **Session Persistence (Database)**
- **Why**: Server restarts or network glitches can't lose debate progress
- **Audit log**: `DebateMessage` table tracks every event (who said what, when timeouts occurred)
- **Recovery**: On reconnect, load full session from DB, resume timeout

### 3. **State Machine (Strict Phase Ordering)**
```
PRO_OPENING → CON_OPENING → PRO_REBUTTAL → CON_REBUTTAL 
           → PRO_CLOSING → CON_CLOSING → DECISION → COMPLETED
```
- **Why**: Prevents replay attacks, out-of-order arguments, accidental state corruption
- **Timeout mechanism**: If human doesn't respond in 5 minutes, their argument is forfeit; system auto-advances

### 4. **Agent Invocation at Right Times**
When phase changes to an agent's turn:
1. Stream the agent's response via LangGraph (real-time tokens to UI)
2. Save final argument to database
3. Auto-advance to next phase
4. If next phase is also agent's turn, invoke agent again (e.g., after Pro agent opens, invoke Con agent)

### 5. **Broadcasting Over Point-to-Point**
- Multiple viewers can watch the same debate
- All receive updates simultaneously
- Graceful disconnection (unregister from broadcast list)

---

## Handling Edge Cases

### Network Disconnect Mid-Argument
```javascript
// Frontend detects WebSocket closed
// User still in textarea with draft
// On reconnect:
// GET /debate/{session_id} → recover phase
// If phase hasn't advanced, offer to resume draft
// If phase advanced, show "your argument was not submitted"
```

### Server Restart During Active Debate
```python
# On startup, resume all incomplete sessions
@app.on_event("startup")
async def recover_sessions():
    db = SessionLocal()
    incomplete = db.query(DebateSession).filter(
        DebateSession.current_phase != DebatePhase.COMPLETED
    ).all()
    for session in incomplete:
        await session_manager.active_sessions[session.id] = session
        await session_manager._schedule_phase_timeout(session.id)
```

### Human Closes Browser → Reconnects 30 Minutes Later
- WebSocket closes → unregister from broadcast
- 30 min later, same browser reconnects with `session_id`
- `/ws/debate/{session_id}` recovers session from DB
- If timeout has passed, debate auto-advanced (human forfeited)
- Full state restored for viewer

---

## Comparison: Agent-Only vs. Human-in-the-Loop

| Aspect | Agent-Only (Current) | Human-in-the-Loop (Proposed) |
|--------|------------|-----------|
| **Communication** | Agent → UI (streaming) | Bidirectional (WebSocket) |
| **Connection** | Single HTTP request (30–90s) | Long-lived WebSocket (minutes–hours) |
| **Session** | Ephemeral (lost on request end) | Persistent (database) |
| **State** | Immutable (request completes) | Mutable (advances on user input) |
| **Concurrency** | None (one debate at a time) | Many (subscribe/broadcast pattern) |
| **Idempotency** | Irrelevant (one-shot) | **N/A** (temporal state machine) |
| **Reconnection** | Restart debate | Resume from DB |

---

## What LangGraph Handles vs. Session Manager

**LangGraph** (computation):
- Run an individual agent node (Pro opening, Con opening, etc.)
- Stream tokens in real-time
- Structured output (winner extraction)

**Session Manager** (orchestration):
- Track whose turn it is
- Enforce timeouts
- Broadcast to multiple viewers
- Persist state across restarts
- Handle reconnections

**They don't overlap**: Session Manager calls LangGraph when it's agent's turn.

---

## Deployment (ECS + WebSocket)

WebSockets work on ECS Fargate if you:
1. Use **ALB** (not NLB) in front of ECS
2. Set target type to `ip`, not `instance`
3. Add ALB stickiness rule (optional—helpful for session affinity)
4. Increase `/proc/sys/net/core/somaxconn` if you expect many concurrent connections

```json
// ecs-task-definition.json addition
"ulimits": [
  {
    "softLimit": 65000,
    "hardLimit": 65000,
    "name": "nofile"
  }
]
```

---

## Summary

The current production guide's HTTP/LangServe approach is **not suitable for human-in-the-loop**. The proper architecture is:

1. **WebSocket** for bidirectional, long-lived communication
2. **Database** for session persistence and recovery
3. **State Machine** (DebatePhase) to enforce turn order and timeouts
4. **LangGraph** invoked by Session Manager at the right turns
5. **Broadcast pattern** to support multiple concurrent viewers

This decouples **computation** (LangGraph) from **orchestration** (Session Manager), making the system:
- Resilient to disconnects and restarts
- Scalable to many concurrent debates
- Auditable (all events logged)
- Testable (Session Manager doesn't need LLM mocks)
