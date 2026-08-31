# Learning Guide: `strands-agents-builder` and `Swarm`

This walks through the two things that are easy to conflate when you first use
this tool: the **`strands` CLI** (a meta-agent that *writes* code for you) and
**`Swarm`** (a multi-agent coordination pattern the *generated* code uses at
runtime). Everything here is grounded in the actual files sitting in this
directory (`pro_agent.py`, `con_agent.py`, `moderator_agent.py`,
`run_debate.py`) and the real errors we hit building them.

---

## 1. Two layers — don't confuse them

| Layer | What it is | When it runs |
|---|---|---|
| **`strands` CLI** (`strands-agents-builder`) | An interactive terminal agent (an agent, itself) whose job is to *write and run Python code* for you from a plain-English prompt | Only while you're actively scaffolding — you type `strands "build me..."` |
| **`strands-agents` SDK** (`import strands`) | The actual Python library — `Agent`, `Swarm`, model providers — that your generated code imports | Every time you run your generated script (`python3 run_debate.py`), forever after |

The CLI is a *builder*. Once it's done writing `pro_agent.py` etc., you don't
need the CLI again — you just run the plain Python files it produced, like
any other script. Nearly all the confusion in this project came from treating
these as one thing instead of two.

---

## 2. Step-by-step: using the `strands` CLI

### 2.1 Install
```bash
pipx install strands-agents-builder
```
This gives you a `strands` command. There's no `strands --version` — check
with `pipx list` instead.

### 2.2 Point it at a model
By default `strands` talks to **Amazon Bedrock**, not Anthropic's API
directly. If you don't have AWS/Bedrock access (as in this project), you must
override it:

```bash
export ANTHROPIC_API_KEY=<your-key>
strands --model-provider anthropic \
        --model-config '{"model_id": "claude-sonnet-4-5", "max_tokens": 8192}' \
        "your prompt here"
```

For `--model-provider anthropic` to exist at all, two things had to be true
in our setup:
1. A `.models/anthropic.py` adapter file exists in the current directory (the
   CLI only ships built-in adapters for `bedrock` and `ollama` — see
   [.models/anthropic.py](.models/anthropic.py) for the ~10-line adapter we added).
2. The `anthropic` PyPI package is installed into the CLI's own pipx-managed
   venv: `pipx inject strands-agents-builder anthropic`.

### 2.3 Run a one-shot prompt
```bash
strands "Build three Strands agents — Pro, Con, and Moderator — for a debate
on 'X'. Use the swarm tool to coordinate them so Pro speaks, then Con speaks,
then Moderator declares a winner. Save the code as separate files."
```
The CLI will narrate what it's doing, write files, and (if you let it) run
the result — all inside one terminal session.

### 2.4 The catch: it wants to ask permission
The CLI's own tools (`file_write`, `editor`, `shell`, `python_repl`) pop a
`Do you want to proceed? [y/*]` prompt before doing anything. In a
non-interactive shell (no TTY) that prompt can never be answered, so every
file write silently fails — you'll see the code narrated in the terminal but
find nothing on disk.

The escape hatch is `BYPASS_TOOL_CONSENT=true`, which skips all those
prompts. **Treat this as what it is: letting an LLM run arbitrary shell
commands and overwrite files with zero human review.** Only use it somewhere
you'd be fine with an unsupervised script running (a scratch directory, not a
shared or production path) — in this project it was blocked by Claude Code's
own safety classifier for exactly that reason.

**What we did instead**: once the CLI narrates working code in the
transcript, you don't need it to *also* be the one that saves and runs it.
Copy/author the files yourself (that's what `pro_agent.py` etc. in this repo
are) and run them with a plain `python3` — no consent-gated tools involved,
because you're not calling the CLI's tools at all anymore, just plain Python.

---

## 3. What `Swarm` actually is

This is the part that's hard to "get" from docs alone, so here's the mental
model that made it click:

> **Swarm is a relay race, not a shared meeting.**
> Only one agent "has the baton" at a time. When it's done, it must
> *physically hand the baton's contents* to the next agent — nothing is
> automatically visible to whoever runs next.

### 3.1 The mechanics
- You construct a `Swarm` with a list of agents (**nodes**) and an
  **entry point** (who goes first).
- Every agent automatically gets a `handoff_to_agent(agent_name, message,
  context)` tool injected into it — you don't write this tool yourself, the
  SDK adds it.
- Whichever agent currently has control runs, produces output, and either:
  - calls `handoff_to_agent("next_agent", message="...")` → control passes to
    that agent, and **the entire message it wrote goes into `message`** — that
    string is *all* the next agent will see of what just happened, or
  - doesn't call it → the swarm decides the task is done and stops.
- There's also an optional `context` dict for structured key/value data, and
  a `shared_context` that accumulates across turns, but the simplest and most
  reliable channel is: **put everything the next agent needs to know directly
  in the handoff `message` text.**

### 3.2 The bug this caused for us (and the fix)
Our first working run had the Moderator say:
> *"I don't have visibility of the actual arguments presented by either
> side... presumably Pro argued..."*

Pro and Con had handed off with short status notes ("the debate now moves to
Con") instead of their actual argument text. The Moderator never lied — it
genuinely never received the arguments, because nothing automatically
carries a full conversation log between swarm nodes.

**Fix**: we edited each agent's `system_prompt` to explicitly require:
> *"Put your COMPLETE argument text verbatim in the handoff message field —
> do not just summarize or say you are done."*

See [pro_agent.py](pro_agent.py) and [con_agent.py](con_agent.py) for the
exact wording. After that change, the Moderator's verdict correctly cited
specific claims from both sides.

### 3.3 Two different things are both called "swarm" — pick the right one
| | `strands_tools.swarm` (a **tool**) | `strands.multiagent.swarm.Swarm` (the **SDK class**) |
|---|---|---|
| What it is | A function an *agent* can call mid-conversation, described by JSON specs (`{"name": ..., "system_prompt": ..., "model_provider": ...}`) | A class *you* construct in your own script from already-built `Agent` objects |
| Model per agent | Sets a `model_provider`/`model_settings` string attribute on each generated agent — **but the SDK never reads these back**, so it's a no-op. Every sub-agent silently falls back to the SDK default (Bedrock) | Each `Agent` already has its real `model=AnthropicModel(...)` set at construction — no ambiguity, no fallback |
| When we used it | The `strands` CLI reached for this by default and it's why our first run kept hitting Bedrock `AccessDenied` even after we told the CLI to use Anthropic | This is what [run_debate.py](run_debate.py) actually uses |

If you only remember one thing from this section: **if an agent in your
swarm needs a specific, non-default model provider, build that `Agent`
yourself with the model set explicitly, and pass the finished objects into
`strands.multiagent.swarm.Swarm(nodes=[...])`.** Don't rely on the
`model_provider` string field inside the `swarm` tool's JSON spec.

### 3.4 How the debate in this repo is wired
```
run_debate.py
  ├─ pro_agent.py       → Agent(name="pro", model=AnthropicModel(...))
  ├─ con_agent.py       → Agent(name="con", model=AnthropicModel(...))
  ├─ moderator_agent.py → Agent(name="moderator", model=AnthropicModel(...))
  └─ Swarm(nodes=[pro, con, moderator], entry_point=pro)
       │
       ▼
  swarm(task)   # runs synchronously, returns a SwarmResult
       │
       ├─ pro turn   → writes argument → handoff_to_agent("con", full_text)
       ├─ con turn   → writes rebuttal → handoff_to_agent("moderator", full_text)
       └─ moderator turn → writes verdict → (no handoff → swarm ends)
```
`result.node_history` gives you the execution order; `result.results[node_id]`
gives you each node's output; `result.status` tells you `COMPLETED` vs
`FAILED`.

---

## 4. Quick reference: gotchas we actually hit

| Symptom | Cause | Fix |
|---|---|---|
| `strands: error: unrecognized arguments: --version` | No `--version` flag exists | Use `pipx list` |
| `ValidationException: model identifier is invalid` | Default Bedrock model ID uses a `us.` cross-region prefix but your AWS region is elsewhere (e.g. `ap-south-1`) | Match region to the profile prefix, or skip Bedrock entirely |
| `AccessDeniedException: ... not authorized to perform bedrock:InvokeModelWithResponseStream` | Your AWS IAM user has no Bedrock permission | Needs an AWS admin to grant it — or bypass Bedrock and use the Anthropic API directly |
| "Can I use my Claude Pro/Max subscription instead of an API key?" | No — Claude Code/claude.ai subscriptions and the Developer API are separate credential systems | Get a standard `sk-ant-...` key from console.anthropic.com |
| `ModuleNotFoundError: No module named 'anthropic'` | The CLI's pipx venv doesn't ship the `anthropic` SDK by default | `pipx inject strands-agents-builder anthropic` |
| `KeyError: 'max_tokens'` when constructing `AnthropicModel` | `max_tokens` is a required config field, easy to forget | Always pass `max_tokens=...` |
| `Do you want to proceed with the file write? [y/*]` hangs forever / file never appears | Non-interactive shell can't answer the CLI's consent prompt | `BYPASS_TOOL_CONSENT=true` (only in a sandbox you trust), or just write/run the code yourself |
| Moderator says it "can't see" the Pro/Con arguments | `handoff_to_agent`'s `message` is the *only* thing the next node sees — nothing is auto-shared | Instruct agents to put the full text verbatim in the handoff message |
| Swarm silently uses Bedrock even after configuring Anthropic | The `strands_tools.swarm` tool's per-agent `model_provider` field is inert | Build `Agent` objects yourself with the model set explicitly; pass them to `strands.multiagent.swarm.Swarm` |

---

## 5. Try it yourself

To adapt this to a new topic or a different trio of agents:
1. Copy `pro_agent.py` → new file, change `name`, `system_prompt`.
2. Repeat for as many agents as you want.
3. In `run_debate.py`, list them in `Swarm(nodes=[...], entry_point=<first>)`
   in the order you want them to *start* in (they still decide when to hand
   off themselves, based on their system prompt).
4. Make sure every prompt explicitly says "put your full output in the
   handoff message" — this is the one instruction that's easy to forget and
   breaks the whole chain silently.
5. Run with:
   ```bash
   export ANTHROPIC_API_KEY=<your-key>
   /Users/anupamg/.local/pipx/venvs/strands-agents-builder/bin/python3 run_debate.py
   ```
