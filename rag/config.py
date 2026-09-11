import os

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Local demo fallback: reuse keys from the original PHP project if this
# Streamlit folder does not have its own .env yet.
if not os.getenv("GROQ_API_KEY") or not os.getenv("GEMINI_API_KEY"):
    sibling_env = os.path.join(
        os.path.dirname(PROJECT_ROOT),
        "AI-Pakistan-Law-Assistant",
        ".env",
    )
    if os.path.isfile(sibling_env):
        load_dotenv(sibling_env, override=False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()

CHUNKS_FILE = os.path.join(PROJECT_ROOT, "docs", "chunks.json")
EMBEDDINGS_FILE = os.path.join(PROJECT_ROOT, "docs", "embeddings.json")

TOP_K = 5
MIN_SCORE = 0.35
QUESTION_MIN_LENGTH = 8
QUESTION_MAX_LENGTH = 1000
HISTORY_TURNS = 3
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = (2, 4, 8)
KNOWLEDGE_BASE_NAME = "Constitution of the Islamic Republic of Pakistan, 1973"
