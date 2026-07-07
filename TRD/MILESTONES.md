# Milestones: Real-Time Multi-Agent Debate Chatbot — MVP

Each milestone groups TRDs that together produce a **testable, runnable increment**. Complete all TRDs in a milestone before moving to the next.

---

## Milestone 1 — Verified Dev Environment & Data Contracts

**TRDs:** TRD1 · TRD2

**Goal:** Prove the environment is healthy and the shared data contracts compile correctly before writing any agent logic. No LLM calls, no graph — just imports and schema validation.

| TRD | Epic | Deliverables |
|-----|------|-------------|
| TRD1 | Repository Scaffolding | `requirements.txt`, `.env`, folder structure, `agents/__init__.py` |
| TRD2 | Shared State & Prompt Templates | `state.py`, `prompts.py`, `build_memory_block()` |

### Test Steps

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   Expected: no dependency conflicts.

2. **Smoke test imports**
   ```bash
   python -c "import langgraph; import langchain_anthropic; import langchain_huggingface; print('OK')"
   ```
   Expected: prints `OK`.

3. **Validate state schema**
   ```bash
   python -c "
   from state import DebateState
   s: DebateState = {
       'topic': 'test', 'round': 'opening',
       'pro_opening': '', 'con_opening': '',
       'pro_rebuttal': '', 'con_rebuttal': '',
       'pro_closing': '', 'con_closing': '',
       'moderator_summary': '', 'winner': '', 'memory_context': []
   }
   print('State OK:', s['topic'])
   "
   ```
   Expected: prints `State OK: test`.

4. **Validate prompt templates**
   ```bash
   python -c "
   from prompts import PRO_OPENING, CON_REBUTTAL, MODERATOR_DECISION, build_memory_block
   assert '{topic}' in PRO_OPENING
   assert '{pro_opening}' in CON_REBUTTAL
   assert build_memory_block([]) == ''
   block = build_memory_block(['past debate summary'])
   assert len(block) <= 1260
   print('Prompts OK')
   "
   ```
   Expected: prints `Prompts OK`.

5. **Verify `.env` loading**
   ```bash
   python -c "
   import os; from dotenv import load_dotenv; load_dotenv()
   key = os.getenv('ANTHROPIC_API_KEY')
   assert key, 'ANTHROPIC_API_KEY missing from .env'
   print('Env OK')
   "
   ```
   Expected: prints `Env OK`.

### Exit Criteria
- [ ] All 5 test steps pass with no errors
- [ ] No placeholder files contain `pass` or `TODO` stubs in `state.py` or `prompts.py`

---

## Milestone 2 — Agent Nodes Callable in Isolation

**TRDs:** TRD3

**Goal:** Each agent node function can be called directly with a hand-crafted state dict and returns the correct partial state update. The LLM is called for the first time here — validate API connectivity and response shape.

| TRD | Epic | Deliverables |
|-----|------|-------------|
| TRD3 | Core Agent Setup | `agents/moderator.py`, `agents/pro.py`, `agents/con.py` |

### Test Steps

1. **Test `moderator_open` (no LLM)**
   ```bash
   python -c "
   import asyncio
   from state import DebateState
   from agents.moderator import moderator_open

   state: DebateState = {'topic': 'AI in hiring', 'round': '', 'pro_opening': '',
       'con_opening': '', 'pro_rebuttal': '', 'con_rebuttal': '',
       'pro_closing': '', 'con_closing': '', 'moderator_summary': '',
       'winner': '', 'memory_context': []}

   result = asyncio.run(moderator_open(state))
   assert result == {'round': 'opening'}, f'Got: {result}'
   print('moderator_open OK')
   "
   ```

2. **Test `moderator_checkpoint` transitions (no LLM)**
   ```bash
   python -c "
   import asyncio
   from agents.moderator import moderator_checkpoint

   for before, expected in [('opening','rebuttal'), ('rebuttal','closing'), ('closing','decision')]:
       state = {'round': before, 'topic': '', 'pro_opening': '', 'con_opening': '',
           'pro_rebuttal': '', 'con_rebuttal': '', 'pro_closing': '', 'con_closing': '',
           'moderator_summary': '', 'winner': '', 'memory_context': []}
       result = asyncio.run(moderator_checkpoint(state))
       assert result['round'] == expected, f'round {before} → expected {expected}, got {result[\"round\"]}'
   print('moderator_checkpoint OK')
   "
   ```

3. **Test `pro_opening` with live LLM call**
   ```bash
   python -c "
   import asyncio
   from agents.pro import pro_opening

   state = {'topic': 'AI should be used in hiring', 'round': 'opening',
       'pro_opening': '', 'con_opening': '', 'pro_rebuttal': '', 'con_rebuttal': '',
       'pro_closing': '', 'con_closing': '', 'moderator_summary': '',
       'winner': '', 'memory_context': []}

   result = asyncio.run(pro_opening(state))
   assert 'pro_opening' in result and len(result['pro_opening']) > 50
   print('pro_opening OK — length:', len(result['pro_opening']))
   "
   ```
   Expected: prints length > 50. Confirms API key works and streaming mode is set.

4. **Test `con_rebuttal` reads Pro's argument**
   ```bash
   python -c "
   import asyncio
   from agents.con import con_rebuttal

   state = {'topic': 'AI in hiring', 'round': 'rebuttal',
       'pro_opening': 'AI improves efficiency and removes bias from screening.',
       'con_opening': '', 'pro_rebuttal': '', 'con_rebuttal': '',
       'pro_closing': '', 'con_closing': '', 'moderator_summary': '',
       'winner': '', 'memory_context': []}

   result = asyncio.run(con_rebuttal(state))
   assert 'con_rebuttal' in result and len(result['con_rebuttal']) > 30
   print('con_rebuttal OK')
   "
   ```

### Exit Criteria
- [ ] All 4 test steps pass
- [ ] `moderator_open` and `moderator_checkpoint` return instantly (no LLM delay)
- [ ] `pro_opening` response is >100 characters
- [ ] `con_rebuttal` prompt demonstrably includes `pro_opening` text (inspect by adding a `print(prompt)` temporarily)

---

## Milestone 3 — Full Debate Runs End-to-End (Blocking Mode)

**TRDs:** TRD4 · TRD5

**Goal:** The complete LangGraph graph executes all 9 nodes in the correct order, the Moderator checkpoint routes through all three round transitions, and the final debate is saved to the vector store. No streaming yet — use blocking `ainvoke` to verify correctness first.

| TRD | Epic | Deliverables |
|-----|------|-------------|
| TRD4 | LangGraph Debate Flow | `graph.py`, compiled `debate_graph`, conditional routing |
| TRD5 | Vector Memory Integration | `memory.py`, `upsert_debate`, `retrieve_context` |

### Test Steps

1. **Import the compiled graph**
   ```bash
   python -c "from graph import debate_graph; print('Graph imported OK')"
   ```

2. **Run a full debate in blocking mode**
   ```python
   # run_test.py — run with: python run_test.py
   import asyncio, os
   from dotenv import load_dotenv
   load_dotenv()

   from graph import debate_graph
   from memory import upsert_debate

   initial_state = {
       "topic": "Should AI be used in hiring?",
       "round": "opening",
       "pro_opening": "", "con_opening": "",
       "pro_rebuttal": "", "con_rebuttal": "",
       "pro_closing": "", "con_closing": "",
       "moderator_summary": "", "winner": "", "memory_context": [],
   }

   async def main():
       final = await debate_graph.ainvoke(initial_state)

       # Verify all fields populated
       for field in ["pro_opening","con_opening","pro_rebuttal","con_rebuttal",
                     "pro_closing","con_closing","moderator_summary","winner"]:
           assert final[field], f"Field '{field}' is empty"

       print("All fields populated ✓")
       print("Winner:", final["winner"])
       print("Round at end:", final["round"])   # should be "decision"

       # Verify memory upsert
       upsert_debate(final)
       print("Memory upsert OK ✓")

   asyncio.run(main())
   ```
   Expected: prints all assertions passed, a winner name, and `Memory upsert OK`.

3. **Verify checkpoint visited 3 times**
   Add a temporary counter to `moderator_checkpoint` and assert it increments to 3 during the run above.

4. **Verify memory retrieval on second run**
   ```python
   # Append to run_test.py and re-run
   from memory import retrieve_context

   context = retrieve_context("Should AI replace recruiters?")
   assert len(context) > 0, "Expected at least 1 similar past debate"
   print(f"Retrieved {len(context)} past debate(s) ✓")
   print("Snippet:", context[0][:100])
   ```
   Expected: retrieves the debate saved in step 2 because the topics are semantically similar.

### Exit Criteria
- [ ] `debate_graph.ainvoke` completes without error
- [ ] All 8 content fields in `DebateState` are non-empty after the run
- [ ] `final["round"]` equals `"decision"` at the end
- [ ] `final["winner"]` is a non-empty string
- [ ] `retrieve_context` returns at least 1 result after upsert
- [ ] Total wall-clock time logged (rough estimate of API cost)

---

## Milestone 4 — Streamed Debate in Jupyter Notebook

**TRDs:** TRD6 · TRD7

**Goal:** The full debate streams token-by-token inside `debate.ipynb` with labelled headers per round. Memory context is shown before the debate starts and the winner is displayed prominently at the end. This milestone is the **demo-ready deliverable**.

| TRD | Epic | Deliverables |
|-----|------|-------------|
| TRD6 | Streaming Output | Streaming event loop, `NODE_LABELS`, status headers, token printing |
| TRD7 | Jupyter Notebook Assembly | `debate.ipynb` with all 7 cells wired and documented |

### Test Steps

1. **Launch Jupyter and open the notebook**
   ```bash
   jupyter notebook debate.ipynb
   ```

2. **First run — fresh kernel (no past debates)**
   - Run **Cell 1** (Setup): confirm `Setup complete.` prints with the correct model name.
   - Run **Cell 2** (Topic): set `topic = "Should AI be used in hiring?"`.
   - Run **Cell 3** (Memory Preview): confirm `No past debates found.` message appears.
   - Run **Cell 4** (Stream): watch tokens stream progressively. Verify:
     - Status label appears before each of the 7 agent turns (6 Pro/Con + 1 Moderator decision)
     - `moderator_open` produces **no visible output** (silent control node)
     - A blank line separates each turn
   - Run **Cell 5** (Winner): confirm winner name and moderator justification display.
   - Run **Cell 6** (Memory Save): confirm upsert confirmation with topic, winner, and excerpts.

3. **Second run — memory evolution demo**
   - **Do not restart the kernel** (memory lives in the kernel process)
   - Go back to **Cell 2**, change topic to `"Should AI replace recruiters?"`
   - Re-run **Cells 2 → 6**
   - In **Cell 3**: confirm at least 1 past debate is shown as context
   - In **Cell 4**: observe that Pro/Con arguments reference or evolve beyond the prior debate's generic points

4. **Kernel restart resilience check**
   - Restart the kernel (`Kernel → Restart`)
   - Re-run **Cell 1**: confirm no import errors
   - Re-run **Cell 3**: confirm memory is empty again (expected — in-memory store resets on restart)

5. **Notebook-to-script conversion check**
   ```bash
   jupyter nbconvert --to script debate.ipynb --output main
   python main.py
   ```
   Expected: script runs without syntax errors (may need minor async wrapper adjustments for CLI context).

### Exit Criteria
- [ ] Notebook runs top-to-bottom on a clean kernel without errors
- [ ] Cell 3 shows "no past debates" on first run, shows retrieved context on second run
- [ ] Cell 4 tokens stream progressively — no full-text delay visible
- [ ] All 7 agent turn labels appear in the correct round order
- [ ] Cell 5 displays winner name prominently
- [ ] Cell 6 shows upsert confirmation
- [ ] `nbconvert` export produces a valid `.py` file

---

## Milestone Summary

| Milestone | TRDs | Testable Outcome | Approx. Effort |
|-----------|------|-----------------|---------------|
| M1 — Dev Environment | TRD1, TRD2 | Imports, schema, prompts all valid | 1 day |
| M2 — Agent Nodes | TRD3 | Each node callable in isolation; first LLM call works | 2–3 days |
| M3 — Full Debate (Blocking) | TRD4, TRD5 | End-to-end debate completes; memory saves and retrieves | 2–3 days |
| M4 — Streamed Notebook Demo | TRD6, TRD7 | Live streaming demo; memory evolution visible across runs | 2 days |
| **Total** | | | **~8–9 days** |
