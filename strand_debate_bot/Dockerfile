# AgentCore Runtime requires linux/arm64, and a container listening on 8080
# with POST /invocations + GET /ping (src/api/routes/agentcore.py) -- see
# openspec/changes/deploy-to-agentcore/design.md, Decision 6.
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY src/ src/

EXPOSE 8080


# ADOT auto-instrumentation for AgentCore Observability (design.md, PRD G8) --
# CloudWatch Transaction Search is an account-level, one-time setting (not
# part of this image); this just emits the spans/traces once that's on.
CMD ["opentelemetry-instrument", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
