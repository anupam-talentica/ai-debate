# Multi-Agent Debate System - Claude Code Guide

## Project Overview

This is a FastAPI-based agentic system featuring LangGraph orchestration of multiple Claude AI agents engaged in structured debates. The system includes persistent memory management and real-time streaming capabilities.

## Tech Stack

- **Backend**: FastAPI + Python
- **Agent Orchestration**: LangGraph
- **LLM**: Claude (via Anthropic SDK)
- **Memory**: In-memory vector storage
- **Deployment**: Docker + Docker Compose
- **API**: RESTful with WebSocket support

## Directory Organization

### Application Structure
```
debate_bot/
├── api/                    # FastAPI route handlers
├── agents/                 # Agent definitions and logic
├── deployment/             # Deployment configurations
├── docs/                   # All documentation (40+ docs, TRDs, guides)
├── tests/                  # Test suite
├── app.py                  # FastAPI application factory
├── server.py               # Server setup and execution
├── graph.py                # LangGraph workflow orchestration
├── state.py                # Type definitions for agent state
├── memory.py               # Memory management and persistence
└── prompts.py              # Agent prompts and templates
```

### Key Files

- **`app.py`** - FastAPI application initialization and configuration
- **`server.py`** - Main server entry point
- **`graph.py`** - LangGraph agent workflow definition
- **`agents/`** - Individual agent implementations (Pro, Con, Moderator)
- **`api/`** - FastAPI route definitions for debate endpoints
- **`Dockerfile`** - Container image definition
- **`docker-compose.yml`** - Local development stack setup

## Environment Setup

```bash
# Copy environment template
cp debate_bot/.env.example debate_bot/.env

# Add your ANTHROPIC_API_KEY to debate_bot/.env
```

## Development Workflow

### Running Locally
```bash
cd debate_bot
python server.py
```

### Running in Docker
```bash
cd debate_bot
docker-compose up
```

### Running Tests
```bash
cd debate_bot
pytest tests/ -v
```

## Common Tasks

### Adding a New Endpoint
1. Create route handler in `api/`
2. Import and register in `app.py`
3. Add tests in `tests/`

### Modifying Agent Behavior
1. Edit prompts in `prompts.py`
2. Update agent logic in `agents/`
3. Modify graph in `graph.py` if workflow changes needed

### Updating Documentation
- General docs: `debate_bot/docs/`
- Technical details: `debate_bot/docs/TRD/` (Technical Reference Documents)
- Quick reference: `debate_bot/QUICKSTART.md`

## Code Style

- Type hints on all function signatures
- Docstrings for public functions
- Follow PEP 8 conventions
- Use FastAPI's built-in validation

## Documentation Resources

- **Architecture**: `debate_bot/docs/ARCHITECTURE.md`
- **Production Guide**: `debate_bot/docs/PRODUCTION_GUIDE.md`
- **Getting Started**: `debate_bot/QUICKSTART.md`
- **Implementation Details**: `debate_bot/docs/IMPLEMENTATION_SUMMARY.md`

## Git Workflow

- Main branch is production-ready
- Feature branches for new work
- Documentation moves to `debate_bot/docs/`
- Keep root directory clean and minimal

## Known Issues & TODOs

- Check `debate_bot/docs/` for project roadmap and known limitations
- Run `pytest` to identify any test failures

## Useful Commands

```bash
# List all API endpoints
grep -r "@app\." debate_bot/api/

# Check test coverage
pytest --cov=debate_bot debate_bot/tests/

# Format code
black debate_bot/

# Type check
mypy debate_bot/
```

## Getting Help

- Review QUICKSTART.md for quick reference
- Check docs/ for detailed documentation
- Review recent commits for context on recent changes
