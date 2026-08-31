import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME", "claude-haiku-4-5-20251001")
MEMORY_PERSIST_DIRECTORY = os.environ.get("MEMORY_PERSIST_DIRECTORY", ".chroma_memory")
SESSION_STORAGE_DIRECTORY = os.environ.get("SESSION_STORAGE_DIRECTORY", ".strands_sessions")
MOCK_LLM = os.environ.get("MOCK_LLM", "false").strip().lower() in ("1", "true", "yes")
MOCK_LLM_DELAY_SECONDS = float(os.environ.get("MOCK_LLM_DELAY_SECONDS", "1.5"))

# AWS deployment target (deploy-to-agentcore design.md, Decisions 4-5). Unset
# by default, which keeps every AWS-backed code path off and the local
# FileSessionManager/ChromaMemoryStore path as-is -- these are additive, not
# a replacement for local dev.
AWS_REGION = os.environ.get("AWS_REGION")
S3_SESSION_BUCKET = os.environ.get("S3_SESSION_BUCKET")
S3_SESSION_PREFIX = os.environ.get("S3_SESSION_PREFIX", "")
S3_VECTORS_BUCKET = os.environ.get("S3_VECTORS_BUCKET")
S3_VECTORS_INDEX = os.environ.get("S3_VECTORS_INDEX", "debates")
BEDROCK_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
