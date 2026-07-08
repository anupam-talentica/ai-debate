# Multi-Agent Debate System

A structured real-time debate platform powered by Claude, featuring three LangGraph agents (Pro, Con, Moderator) with in-memory vector storage for cross-debate memory evolution.

## Project Structure

```
├── debate_bot/                 # Main application
│   ├── src/                   # Core application code (future organization)
│   ├── api/                   # API endpoints
│   ├── agents/                # LangGraph agent definitions
│   ├── deployment/            # Deployment configurations (Docker, K8s)
│   ├── docs/                  # Comprehensive documentation
│   │   ├── ARCHITECTURE.md    # System architecture
│   │   ├── PRODUCTION_GUIDE.md # Production deployment guide
│   │   ├── QUICKSTART.md      # Quick start guide
│   │   └── TRD/               # Technical reference documents
│   ├── tests/                 # Test suite
│   ├── app.py                 # FastAPI application entry point
│   ├── server.py              # Server configuration
│   ├── graph.py               # LangGraph workflow
│   ├── state.py               # Agent state definitions
│   ├── memory.py              # Memory management
│   ├── prompts.py             # Agent prompts
│   ├── Dockerfile             # Container configuration
│   ├── docker-compose.yml     # Docker Compose setup
│   ├── requirements.txt        # Python dependencies
│   └── README.md              # App-specific documentation
├── .claude/                    # Claude Code configuration
├── .debatenv/                  # Python virtual environment
└── README.md                   # This file
```

## Quick Start

```bash
cd debate_bot
cp .env.example .env           # Add your ANTHROPIC_API_KEY
pip install -r requirements.txt
python server.py
```

## Documentation

- **[Architecture Guide](debate_bot/docs/ARCHITECTURE.md)** - System design and agent structure
- **[Production Guide](debate_bot/docs/PRODUCTION_GUIDE.md)** - Deployment and operations
- **[Quick Start](debate_bot/QUICKSTART.md)** - Get up and running in minutes
- **[Technical Reference Documents](debate_bot/docs/)** - Deep dive into technical details

## Development

### Running Tests
```bash
cd debate_bot
pytest tests/
```

### Using Docker
```bash
cd debate_bot
docker-compose up
```

## Technologies

- **Framework**: FastAPI + LangGraph
- **LLM**: Claude (Anthropic)
- **Memory**: In-memory vector storage
- **Containerization**: Docker

## License

Proprietary - Talentica Software
