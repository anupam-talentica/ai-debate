# Production Readiness Guide — Real-Time Multi-Agent Debate Chatbot

This guide walks you from the current MVP (Jupyter notebook) to a production-ready service. It covers **Testing**, **Deployment**, and **Monitoring** using LangChain/LangSmith and AWS frameworks.

---

## Table of Contents

1. [Current Architecture Summary](#1-current-architecture-summary)
2. [Step 1 — Convert Notebook to a Python Module](#2-step-1--convert-notebook-to-a-python-module)
3. [Step 2 — Testing](#3-step-2--testing)
   - Unit Tests
   - Integration Tests with LangSmith Evaluation
   - End-to-End Tests
4. [Step 3 — Monitoring with LangSmith](#4-step-3--monitoring-with-langsmith)
5. [Step 4 — Deployment Options](#5-step-4--deployment-options)
   - Option A: LangServe + Docker + AWS ECS
   - Option B: AWS Lambda + API Gateway (Serverless)
6. [Step 5 — Persistent Memory for Production](#6-step-5--persistent-memory-for-production)
7. [Step 6 — CI/CD Pipeline](#7-step-6--cicd-pipeline)
8. [Step 7 — Secrets Management](#8-step-7--secrets-management)
9. [Production Readiness Checklist](#9-production-readiness-checklist)

---

## 1. Current Architecture Summary

| Component | Current (MVP) | Production Target |
|-----------|--------------|-------------------|
| Orchestration | LangGraph `StateGraph` | LangGraph (unchanged) |
| LLM | Claude Haiku 4.5 via `langchain-anthropic` | Same + LangSmith tracing |
| Memory | `InMemoryVectorStore` (lost on restart) | Chroma DB / Pinecone |
| Serving | Jupyter Notebook | LangServe (FastAPI) or AWS Lambda |
| Monitoring | None | LangSmith + AWS CloudWatch |
| Secrets | `.env` file | AWS Secrets Manager |
| CI/CD | None | GitHub Actions |

---

## 2. Step 1 — Convert Notebook to a Python Module

The notebook `debate.ipynb` must become an importable, testable Python module before it can be deployed or tested in CI.

### Create `app.py` — Main Application Entry Point

```python
# debate_bot/app.py
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from graph import build_graph
from memory import MemoryStore

memory_store = MemoryStore()
graph = build_graph(memory_store)

async def run_debate(topic: str) -> dict:
    """Run a full debate and return the final state."""
    initial_state = {
        "topic": topic,
        "round": "",
        "pro_opening": "",
        "con_opening": "",
        "pro_rebuttal": "",
        "con_rebuttal": "",
        "pro_closing": "",
        "con_closing": "",
        "moderator_summary": "",
        "winner": "",
        "memory_context": [],
    }
    final_state = await graph.ainvoke(initial_state)
    memory_store.upsert_debate(final_state)
    return final_state

if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI will replace software engineers"
    result = asyncio.run(run_debate(topic))
    print(f"\nWinner: {result['winner']}")
    print(f"Summary: {result['moderator_summary']}")
```

### Update `requirements.txt` for Production

```
# Core
langgraph>=0.2
langchain-anthropic>=0.2
langchain-core>=0.3
langchain-huggingface>=0.1
sentence-transformers>=3.0
python-dotenv>=1.0

# Serving (LangServe)
langserve[all]>=0.3
fastapi>=0.110
uvicorn>=0.27

# Monitoring
langsmith>=0.1
opentelemetry-sdk>=1.20

# Testing
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12

# Production persistence
chromadb>=0.5         # swap for Pinecone SDK if using managed vector DB
boto3>=1.34           # AWS SDK for Secrets Manager, CloudWatch
```

---

## 3. Step 2 — Testing

### 3.1 Unit Tests

Unit tests mock the Anthropic API so they run fast in CI with zero cost.

```
debate_bot/
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_state.py
    ├── test_agents.py
    ├── test_memory.py
    └── test_graph.py
```

**`tests/conftest.py`** — Shared fixtures

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm():
    """Returns a mock LLM that returns a fixed string for any invoke."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="Mock argument text."))
    return llm

@pytest.fixture
def base_state():
    return {
        "topic": "AI will replace software engineers",
        "round": "opening",
        "pro_opening": "",
        "con_opening": "",
        "pro_rebuttal": "",
        "con_rebuttal": "",
        "pro_closing": "",
        "con_closing": "",
        "moderator_summary": "",
        "winner": "",
        "memory_context": [],
    }
```

**`tests/test_agents.py`** — Test individual agent nodes

```python
# tests/test_agents.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_pro_opening_populates_state(base_state, mock_llm):
    """Pro agent must write a non-empty opening argument."""
    with patch("agents.pro.ChatAnthropic", return_value=mock_llm):
        from agents.pro import pro_opening_node
        result = await pro_opening_node(base_state)
    assert result["pro_opening"] != ""

@pytest.mark.asyncio
async def test_con_opening_reads_pro_argument(base_state, mock_llm):
    """Con agent must receive the pro opening as context."""
    base_state["pro_opening"] = "AI is superior at coding tasks."
    with patch("agents.con.ChatAnthropic", return_value=mock_llm):
        from agents.con import con_opening_node
        result = await con_opening_node(base_state)
    assert result["con_opening"] != ""

@pytest.mark.asyncio
async def test_moderator_decision_sets_winner(base_state, mock_llm):
    """Moderator must declare a winner (Pro or Con)."""
    base_state.update({
        "pro_closing": "AI is transformative.",
        "con_closing": "Humans are irreplaceable.",
        "round": "decision",
    })
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(content="Winner: Pro. The pro side argued more effectively.")
    )
    with patch("agents.moderator.ChatAnthropic", return_value=mock_llm):
        from agents.moderator import moderator_decision_node
        result = await moderator_decision_node(base_state)
    assert result["winner"] in ("Pro", "Con")
    assert result["moderator_summary"] != ""
```

**`tests/test_memory.py`** — Test vector store retrieval

```python
# tests/test_memory.py
import pytest
from memory import MemoryStore

def test_upsert_and_retrieve():
    """Memory store must return relevant past debates."""
    store = MemoryStore()
    store.upsert_debate({
        "topic": "AI will replace software engineers",
        "winner": "Pro",
        "moderator_summary": "Pro argued AI automates repetitive coding tasks.",
    })
    results = store.retrieve_context("Will AI take coding jobs?", k=1)
    assert len(results) == 1
    assert "Pro" in results[0] or "AI" in results[0]

def test_empty_store_returns_empty_list():
    store = MemoryStore()
    results = store.retrieve_context("Anything", k=2)
    assert results == []
```

**`tests/test_graph.py`** — Test LangGraph routing logic

```python
# tests/test_graph.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from memory import MemoryStore

@pytest.mark.asyncio
async def test_full_graph_runs_to_completion():
    """End-to-end graph execution must populate all state fields."""
    with patch("langchain_anthropic.ChatAnthropic") as MockLLM:
        instance = MockLLM.return_value
        instance.ainvoke = AsyncMock(
            return_value=MagicMock(content="Winner: Pro. Strong arguments.")
        )
        instance.astream = AsyncMock(return_value=aiter(["Token1", "Token2"]))

        from graph import build_graph
        from memory import MemoryStore
        graph = build_graph(MemoryStore())
        state = await graph.ainvoke({
            "topic": "Remote work is better than office work",
            "round": "", "pro_opening": "", "con_opening": "",
            "pro_rebuttal": "", "con_rebuttal": "",
            "pro_closing": "", "con_closing": "",
            "moderator_summary": "", "winner": "", "memory_context": [],
        })

    assert state["winner"] in ("Pro", "Con")
    assert state["pro_opening"] != ""
    assert state["con_opening"] != ""
    assert state["moderator_summary"] != ""

async def aiter(items):
    for item in items:
        yield item
```

### Run Tests

```bash
cd debate_bot
pytest tests/ -v --asyncio-mode=auto
```

---

### 3.2 Integration Tests with LangSmith Evaluation

LangSmith provides a dataset-based evaluation framework to measure debate quality over time.

**Step 1 — Set up LangSmith**

```bash
pip install langsmith
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-langsmith-key>
export LANGCHAIN_PROJECT="debate-bot-eval"
```

**Step 2 — Create an evaluation dataset**

```python
# scripts/create_eval_dataset.py
from langsmith import Client

client = Client()
dataset = client.create_dataset("debate-topics-v1", description="Standard debate topics for regression testing")

examples = [
    {"inputs": {"topic": "AI will replace software engineers"}, "outputs": {"expected_winner_options": ["Pro", "Con"]}},
    {"inputs": {"topic": "Remote work is more productive than office work"}, "outputs": {"expected_winner_options": ["Pro", "Con"]}},
    {"inputs": {"topic": "Social media does more harm than good"}, "outputs": {"expected_winner_options": ["Pro", "Con"]}},
]

for example in examples:
    client.create_example(
        inputs=example["inputs"],
        outputs=example["outputs"],
        dataset_id=dataset.id,
    )
print(f"Created dataset: {dataset.id}")
```

**Step 3 — Write evaluators**

```python
# scripts/run_eval.py
import asyncio
from langsmith import Client
from langsmith.evaluation import evaluate, LangChainStringEvaluator
from app import run_debate

client = Client()

def debate_target(inputs: dict) -> dict:
    """Wrapper to run debate synchronously for the evaluator."""
    result = asyncio.run(run_debate(inputs["topic"]))
    return {
        "winner": result["winner"],
        "pro_argument": result["pro_opening"],
        "con_argument": result["con_opening"],
        "summary": result["moderator_summary"],
    }

def check_winner_valid(run, example) -> dict:
    """Custom evaluator: winner must be 'Pro' or 'Con'."""
    winner = run.outputs.get("winner", "")
    return {"score": 1 if winner in ("Pro", "Con") else 0, "key": "valid_winner"}

def check_summary_non_empty(run, example) -> dict:
    summary = run.outputs.get("summary", "")
    return {"score": 1 if len(summary) > 20 else 0, "key": "summary_quality"}

results = evaluate(
    debate_target,
    data="debate-topics-v1",
    evaluators=[check_winner_valid, check_summary_non_empty],
    experiment_prefix="debate-bot",
)
print(results.to_pandas())
```

```bash
python scripts/run_eval.py
```

---

### 3.3 End-to-End Tests (Staging Environment)

Once deployed (see Step 4), add E2E tests that hit the live API:

```python
# tests/test_e2e.py
import httpx
import pytest

BASE_URL = "http://localhost:8000"  # or staging URL

def test_debate_endpoint_returns_winner():
    response = httpx.post(
        f"{BASE_URL}/debate/invoke",
        json={"input": {"topic": "Universal basic income should be implemented"}},
        timeout=120.0,
    )
    assert response.status_code == 200
    output = response.json()["output"]
    assert output["winner"] in ("Pro", "Con")
    assert len(output["moderator_summary"]) > 20

def test_debate_endpoint_rejects_empty_topic():
    response = httpx.post(
        f"{BASE_URL}/debate/invoke",
        json={"input": {"topic": ""}},
        timeout=10.0,
    )
    assert response.status_code == 422
```

---

## 4. Step 3 — Monitoring with LangSmith

LangSmith captures every LLM call, token count, latency, and prompt trace automatically.

### 4.1 Enable Tracing (One-Line Change)

Add these environment variables to your `.env`:

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your-langsmith-key>
LANGCHAIN_PROJECT=debate-bot-prod
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

**That's it.** Because the debate bot already uses `langchain-anthropic` and `langgraph`, every node execution, LLM call, token count, and prompt is automatically traced. No code changes needed.

### 4.2 Add Custom Metadata to Traces

Tag traces with debate-specific context for filtering in the LangSmith dashboard:

```python
# graph.py — wrap graph invocation with run metadata
from langsmith import traceable

@traceable(name="debate-run", metadata={"version": "1.0"})
async def run_debate_traced(topic: str) -> dict:
    from app import run_debate
    result = await run_debate(topic)
    # Add custom tags to the trace
    from langsmith.run_helpers import get_current_run_tree
    run = get_current_run_tree()
    if run:
        run.end(outputs={"winner": result["winner"], "topic": topic})
    return result
```

### 4.3 LangSmith Dashboard — Key Metrics to Monitor

After running debates, visit `https://smith.langchain.com` and track:

| Metric | Where to Find | Alert Threshold |
|--------|--------------|-----------------|
| **Token usage per debate** | Traces > Token Usage | > 8,000 tokens (cost spike) |
| **Total debate latency** | Traces > Latency | > 90 seconds |
| **Per-node latency** | Traces > Node breakdown | Pro/Con > 20s each |
| **LLM error rate** | Traces > Status | > 1% errors |
| **Memory retrieval relevance** | Custom evaluator score | < 0.7 similarity score |

### 4.4 Add CloudWatch Structured Logging (AWS)

```python
# debate_bot/logger.py
import json
import logging
import sys

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_object = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "debate_topic"):
            log_object["debate_topic"] = record.debate_topic
        if hasattr(record, "winner"):
            log_object["winner"] = record.winner
        if hasattr(record, "token_count"):
            log_object["token_count"] = record.token_count
        return json.dumps(log_object)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
```

Use it in `app.py`:

```python
from logger import get_logger
logger = get_logger("debate-bot")

async def run_debate(topic: str) -> dict:
    logger.info("Debate started", extra={"debate_topic": topic})
    final_state = await graph.ainvoke(initial_state)
    logger.info(
        "Debate completed",
        extra={
            "debate_topic": topic,
            "winner": final_state["winner"],
        }
    )
    return final_state
```

CloudWatch Logs Insights query to find all debates and winners:

```
fields @timestamp, debate_topic, winner
| filter level = "INFO" and message = "Debate completed"
| sort @timestamp desc
| limit 50
```

---

## 5. Step 4 — Deployment Options

**Recommendation: Use Option A (ECS) for production.** Option B (Lambda) is not suitable for long-running tasks like the debate bot due to scale-to-zero risks and task loss.

| Option | Best For | Complexity | Cost | Recommended |
|--------|----------|------------|------|-------------|
| **A: LangServe + ECS** | Production debates (streaming, monitoring) | Medium | ~$30-80/mo | ✅ Yes |
| **B: Lambda + API Gateway** | ⚠️ Not recommended for production | Low | Pay-per-use | ❌ No |

---

### Option A: LangServe + Docker + AWS ECS (Recommended)

#### 4A.1 — Create a LangServe App

LangServe wraps your LangGraph graph as a FastAPI endpoint with streaming support out of the box.

```python
# debate_bot/server.py
from fastapi import FastAPI
from langserve import add_routes
from langchain_core.runnables import RunnableLambda
from app import run_debate, graph
import uvicorn

app = FastAPI(title="Debate Bot API", version="1.0")

# Wrap the async debate runner as a LangChain Runnable
debate_runnable = RunnableLambda(
    lambda input: __import__("asyncio").get_event_loop().run_until_complete(
        run_debate(input["topic"])
    )
)

# Mount at /debate — auto-generates /debate/invoke, /debate/stream, /debate/batch
add_routes(app, debate_runnable, path="/debate", input_type=dict, output_type=dict)

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```bash
# Test locally
pip install langserve[all]
python server.py

# In another terminal
curl -X POST http://localhost:8000/debate/invoke \
  -H "Content-Type: application/json" \
  -d '{"input": {"topic": "AI will replace software engineers"}}'
```

The `/debate/stream` endpoint provides token-level streaming to a web client.

#### 4A.2 — Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps for sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download embedding model at build time (avoids cold-start delay)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build and test locally
docker build -t debate-bot:latest .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e LANGCHAIN_API_KEY=$LANGCHAIN_API_KEY \
  -e LANGCHAIN_TRACING_V2=true \
  debate-bot:latest
```

#### 4A.3 — Push to AWS ECR

```bash
# Set your AWS region and account ID
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/debate-bot

# Create ECR repository (one-time)
aws ecr create-repository --repository-name debate-bot --region $AWS_REGION

# Login, tag, and push
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ECR_REPO
docker tag debate-bot:latest $ECR_REPO:latest
docker push $ECR_REPO:latest
```

#### 4A.4 — Deploy to AWS ECS Fargate

```json
// ecs-task-definition.json
{
  "family": "debate-bot",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "debate-bot",
      "image": "ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/debate-bot:latest",
      "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
      "secrets": [
        {"name": "ANTHROPIC_API_KEY", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:debate-bot/anthropic-key"},
        {"name": "LANGCHAIN_API_KEY", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:debate-bot/langsmith-key"}
      ],
      "environment": [
        {"name": "LANGCHAIN_TRACING_V2", "value": "true"},
        {"name": "LANGCHAIN_PROJECT", "value": "debate-bot-prod"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/debate-bot",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      }
    }
  ]
}
```

```bash
# Register task and create service
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json

aws ecs create-service \
  --cluster debate-bot-cluster \
  --service-name debate-bot-service \
  --task-definition debate-bot \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxx],securityGroups=[sg-xxxx],assignPublicIp=ENABLED}"
```

#### 4A.5 — CloudWatch Dashboard & Alarms

```bash
# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/debate-bot

# Create alarm for high error rate
aws cloudwatch put-metric-alarm \
  --alarm-name "debate-bot-errors" \
  --metric-name "HTTPCode_Target_5XX_Count" \
  --namespace "AWS/ApplicationELB" \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:debate-bot-alerts

# Create alarm for high debate latency (if publishing custom metrics)
aws cloudwatch put-metric-alarm \
  --alarm-name "debate-bot-high-latency" \
  --metric-name "DebateLatencySeconds" \
  --namespace "DebateBot/Metrics" \
  --statistic Average \
  --period 300 \
  --threshold 120 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:debate-bot-alerts
```

---

### Option B: AWS Lambda + API Gateway (Serverless) — ⚠️ Not Recommended

**IMPORTANT: LangSmith discourages this approach for production debate bots.** Full debates take 60-90 seconds, and Lambda's scale-to-zero behavior creates two critical problems:
1. **Task Loss**: If Lambda scales down during a debate, the in-flight computation is lost, leaving requests hanging or returning errors.
2. **Unreliable Scaling**: Lambda's scaling-up latency (cold starts: 10–15 seconds) can exceed individual timeouts, causing cascading failures.

Even with async invocation or Step Functions, you lose observability into the long-running task and introduce operational complexity. **Use Option A (ECS) instead** for any production workload.

If you must use serverless (e.g., low-budget prototype), use a managed Step Functions state machine with longer timeouts and retry policies — but accept reduced reliability.

#### 4B.1 — Lambda Handler

```python
# lambda_handler.py
import asyncio
import json
import boto3
import os

# Initialize outside handler for connection reuse
from app import run_debate

def handler(event, context):
    """Synchronous Lambda entry point."""
    body = json.loads(event.get("body", "{}"))
    topic = body.get("topic", "")

    if not topic:
        return {"statusCode": 400, "body": json.dumps({"error": "topic is required"})}

    result = asyncio.run(run_debate(topic))

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "winner": result["winner"],
            "summary": result["moderator_summary"],
            "topic": topic,
        }),
    }
```

#### 4B.2 — Deploy with AWS SAM

```yaml
# template.yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Globals:
  Function:
    Timeout: 180  # 3-minute timeout for full debate
    MemorySize: 1024  # sentence-transformers needs memory

Resources:
  DebateBotFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: lambda_handler.handler
      Runtime: python3.11
      CodeUri: .
      Environment:
        Variables:
          LANGCHAIN_TRACING_V2: "true"
          LANGCHAIN_PROJECT: "debate-bot-prod"
      Events:
        DebateApi:
          Type: Api
          Properties:
            Path: /debate
            Method: post
      Policies:
        - AWSSecretsManagerGetSecretValuePolicy:
            SecretArn: !Sub "arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:debate-bot/*"

Outputs:
  DebateApiUrl:
    Value: !Sub "https://${ServerlessRestApi}.execute-api.${AWS::Region}.amazonaws.com/Prod/debate"
```

```bash
# Build and deploy
pip install aws-sam-cli
sam build
sam deploy --guided
```

---

## 6. Step 5 — Persistent Memory for Production

The current `InMemoryVectorStore` is lost on every restart. Replace it with a persistent store for production.

### Option: Chroma DB (Self-Hosted)

```python
# memory.py — production version
import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

class MemoryStore:
    def __init__(self, persist_directory: str = "/data/chroma"):
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.store = Chroma(
            collection_name="debates",
            embedding_function=self.embeddings,
            persist_directory=persist_directory,
        )

    def upsert_debate(self, state: dict) -> None:
        doc = f"Topic: {state['topic']}\nWinner: {state['winner']}\nSummary: {state['moderator_summary']}"
        self.store.add_texts([doc], metadatas=[{"topic": state["topic"], "winner": state["winner"]}])

    def retrieve_context(self, topic: str, k: int = 2) -> list[str]:
        results = self.store.similarity_search(topic, k=k)
        return [doc.page_content for doc in results]
```

Add to `Dockerfile`:
```dockerfile
RUN pip install langchain-chroma chromadb
VOLUME ["/data/chroma"]
```

---

## 7. Step 6 — CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Test, Build & Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -r debate_bot/requirements.txt
      - name: Run unit tests
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          cd debate_bot
          pytest tests/ -v --asyncio-mode=auto -k "not e2e"
      - name: Run LangSmith evaluation (main only)
        if: github.ref == 'refs/heads/main'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          LANGCHAIN_API_KEY: ${{ secrets.LANGCHAIN_API_KEY }}
          LANGCHAIN_TRACING_V2: "true"
        run: python scripts/run_eval.py

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2
      - name: Build and push Docker image
        run: |
          cd debate_bot
          docker build -t ${{ secrets.ECR_REGISTRY }}/debate-bot:${{ github.sha }} .
          docker push ${{ secrets.ECR_REGISTRY }}/debate-bot:${{ github.sha }}
      - name: Update ECS service
        run: |
          aws ecs update-service \
            --cluster debate-bot-cluster \
            --service debate-bot-service \
            --force-new-deployment
```

---

## 8. Step 7 — Secrets Management

Never store API keys in environment files in production. Use AWS Secrets Manager.

```bash
# Store secrets in AWS Secrets Manager
aws secretsmanager create-secret \
  --name debate-bot/anthropic-key \
  --secret-string '{"ANTHROPIC_API_KEY": "sk-ant-..."}'

aws secretsmanager create-secret \
  --name debate-bot/langsmith-key \
  --secret-string '{"LANGCHAIN_API_KEY": "ls__..."}'
```

Retrieve secrets at startup in `app.py`:

```python
# debate_bot/config.py
import boto3
import json
import os

def load_secrets():
    """Load secrets from AWS Secrets Manager if running in AWS."""
    if not os.getenv("AWS_EXECUTION_ENV"):
        return  # Running locally — use .env file
    client = boto3.client("secretsmanager", region_name="us-east-1")
    for secret_name, env_var in [
        ("debate-bot/anthropic-key", "ANTHROPIC_API_KEY"),
        ("debate-bot/langsmith-key", "LANGCHAIN_API_KEY"),
    ]:
        try:
            value = client.get_secret_value(SecretId=secret_name)
            secrets = json.loads(value["SecretString"])
            os.environ.update(secrets)
        except Exception as e:
            print(f"Warning: could not load secret {secret_name}: {e}")
```

Call `load_secrets()` at the top of `app.py` before any LangChain imports.

---

## 9. Production Readiness Checklist

Work through this before your first production deployment.

### Testing
- [ ] Unit tests pass for Pro, Con, and Moderator agent nodes
- [ ] Memory store upsert and retrieval tests pass
- [ ] Full graph execution test passes with mocked LLM
- [ ] LangSmith evaluation dataset created with ≥5 debate topics
- [ ] E2E test runs against staging environment

### Code Quality
- [ ] Notebook converted to Python module (`app.py`, `server.py`)
- [ ] Moderator winner extraction is robust (regex or structured output, not string contains)
- [ ] All `InMemoryVectorStore` usages replaced with Chroma DB or Pinecone
- [ ] API key loading uses AWS Secrets Manager in production

### Deployment
- [ ] `Dockerfile` builds successfully
- [ ] Container starts and `/health` returns `200`
- [ ] ECS task definition registered with correct CPU/memory
- [ ] ECS service running with ≥1 healthy task
- [ ] API Gateway or ALB configured in front of ECS service
- [ ] Timeout set to ≥180 seconds (debates take 60-90s)

### Monitoring
- [ ] `LANGCHAIN_TRACING_V2=true` in production environment
- [ ] LangSmith project `debate-bot-prod` receives traces
- [ ] CloudWatch log group `/ecs/debate-bot` receives JSON logs
- [ ] CloudWatch alarm on 5xx error rate
- [ ] CloudWatch alarm on debate latency > 120 seconds
- [ ] SNS topic configured for alarm notifications

### Security
- [ ] No API keys in source code or Docker image
- [ ] Secrets stored in AWS Secrets Manager
- [ ] ECS task role has minimal IAM permissions (Secrets Manager read-only)
- [ ] Security group restricts inbound to port 8000 only from ALB

### CI/CD
- [ ] GitHub Actions workflow runs tests on every PR
- [ ] Deployment only happens on merge to `main`
- [ ] LangSmith evaluation runs on every main deployment

---

## Quick Reference — Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic Claude API key |
| `MODEL_NAME` | No | Defaults to `claude-haiku-4-5-20251001` |
| `HF_TOKEN` | No | HuggingFace token (only needed for gated models) |
| `LANGCHAIN_TRACING_V2` | Prod | Set to `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | Prod | LangSmith API key |
| `LANGCHAIN_PROJECT` | Prod | LangSmith project name (e.g. `debate-bot-prod`) |
| `LANGCHAIN_ENDPOINT` | No | Defaults to `https://api.smith.langchain.com` |
| `CHROMA_PERSIST_DIR` | Prod | Path to Chroma DB persistence directory |
