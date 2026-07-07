# TRD1 — Epic 0: Repository Scaffolding

## Goal
Create the project skeleton, install dependencies, and verify the dev environment is working before any agent code is written.

---

## Deliverables

| File / Folder | Purpose |
|---------------|---------|
| `requirements.txt` | All Python dependencies pinned to minor versions |
| `.env.example` | Template listing all required environment variables |
| `.env` | Local copy (git-ignored) with real credentials |
| `.gitignore` | Excludes `.env`, `__pycache__`, `.ipynb_checkpoints` |
| `agents/__init__.py` | Makes `agents/` a package |
| `README.md` | One-paragraph setup instructions |

---

## Requirements

### R1.1 — Dependency File
`requirements.txt` must include:

```
langgraph>=0.2
langchain-anthropic>=0.2
langchain-core>=0.3
langchain-huggingface>=0.1
sentence-transformers>=3.0
python-dotenv>=1.0
jupyter>=1.0
```

### R1.2 — Environment Variables
`.env.example` must define:

```
ANTHROPIC_API_KEY=sk-ant-...
MODEL_NAME=claude-haiku-4-5-20251001
```

The application must exit with a descriptive error if `ANTHROPIC_API_KEY` is not set.

### R1.3 — Folder Structure
The following directories and empty placeholder files must exist before any module code is written:

```
agents/
    __init__.py
    moderator.py
    pro.py
    con.py
state.py
prompts.py
memory.py
graph.py
debate.ipynb
```

### R1.4 — Smoke Test
After setup, the following must run without error:

```bash
pip install -r requirements.txt
python -c "import langgraph; import langchain_anthropic; print('OK')"
```

---

## Acceptance Criteria

- [ ] `pip install -r requirements.txt` completes without conflicts
- [ ] `.env.example` is committed; `.env` is git-ignored
- [ ] All placeholder files and folders exist
- [ ] Smoke test prints `OK`

---

## Dependencies
None — this is the first task.
