# PRD: Real-Time Multi-Agent Debate Chatbot — MVP

## Context
Build the smallest working version of a multi-agent debate chatbot that demonstrates core value: three agents (Moderator, Pro, Con) run a structured debate on a user-supplied topic, stream output live, and use basic vector memory to avoid repeating identical arguments across debates. Everything not needed for a working demo is deferred.

---

## MVP Scope
- Three agents, one LLM (e.g., Claude or GPT-4o via API)
- Four debate rounds: Opening → Rebuttal → Closing → Moderator Decision
- Streamed terminal output
- Local vector store (ChromaDB) for memory
- Single-command CLI entrypoint

---

## Epic 1: Core Agent Setup

| Story ID | Description | Why | Acceptance Criteria | Priority |
|----------|-------------|-----|---------------------|----------|
| S_1.1 | As a system, create a Moderator agent that assigns turns and enforces round order | So that the debate follows a predictable structure without manual coordination | Moderator triggers Pro → Con → Pro → Con → Moderator in correct sequence | Must-Have |
| S_1.2 | As a system, create a Pro agent that generates arguments in favor of the topic | So that the debate has an affirmative voice | Pro produces an opening (~200 words), rebuttal (~100 words), and closing (~75 words) | Must-Have |
| S_1.3 | As a system, create a Con agent that generates counter-arguments | So that the debate has an opposing voice | Con produces the same three turn types as Pro, directly referencing Pro's prior arguments | Must-Have |
| S_1.4 | As a developer, define a minimal shared message schema (role, round, content) | So that agents can read each other's outputs without custom parsing | All agents produce and consume the same dict/dataclass structure | Must-Have |

---

## Epic 2: Debate Flow

| Story ID | Description | Why | Acceptance Criteria | Priority |
|----------|-------------|-----|---------------------|----------|
| S_2.1 | As a user, run a full four-round debate from a single topic input | So that the entire experience is end-to-end with no manual steps | All four rounds complete automatically in order for any valid topic string | Must-Have |
| S_2.2 | As a Moderator, summarize both sides and declare a winner at the end | So that every debate has a clear outcome | Final Moderator output names the winner with a one-paragraph justification | Must-Have |
| S_2.3 | As a developer, ensure each rebuttal receives the opposing agent's most recent argument as context | So that the debate is interactive, not two parallel monologues | Rebuttal prompt includes the prior opposing turn; verified by inspecting the prompt payload | Must-Have |

---

## Epic 3: Streaming Output

| Story ID | Description | Why | Acceptance Criteria | Priority |
|----------|-------------|-----|---------------------|----------|
| S_3.1 | As a user, see a status label before each agent turn (e.g., "Pro Agent — Opening Round") | So that it is always clear who is speaking and which round is active | Label prints to stdout before every agent response | Must-Have |
| S_3.2 | As a user, see each agent's text streamed token-by-token | So that the debate feels live rather than appearing as a wall of text | LLM streaming is enabled; output appears progressively with no full-text delay | Must-Have |

---

## Epic 4: Vector Memory (Basic)

| Story ID | Description | Why | Acceptance Criteria | Priority |
|----------|-------------|-----|---------------------|----------|
| S_4.1 | As a system, save each completed debate (topic + key arguments + outcome) to ChromaDB | So that past debates are available for future retrieval | Record is upserted after every debate; verified with a DB query | Must-Have |
| S_4.2 | As an agent, retrieve the top-2 most semantically similar past debates before generating arguments | So that agents evolve their reasoning instead of repeating the same generic points | Retrieved context is injected into the agent system prompt; gracefully empty if no past debates exist | Must-Have |

---

## Epic 5: CLI Entrypoint & Setup

| Story ID | Description | Why | Acceptance Criteria | Priority |
|----------|-------------|-----|---------------------|----------|
| S_5.1 | As a user, start a debate with `python main.py --topic "..."` | So that the demo requires no UI or server setup | Command runs end-to-end; `--topic` is required; missing topic shows a usage error | Must-Have |
| S_5.2 | As a developer, configure LLM API key and model via `.env` | So that credentials are never hardcoded | `.env.example` documents all required vars; app exits with a clear error if any are missing | Must-Have |

---

## Deferred (Post-MVP)
- Web UI or streaming API endpoint
- Moderator memory-relevance filtering
- Multiple vector DB backends (Pinecone, Weaviate)
- Word-count enforcement and validation
- Structured logging / observability
- Automated test suite

---

## Effort Summary
All MVP stories are Small–Medium (≤ 2 days each). Full MVP is estimated at **8–10 developer days**.
