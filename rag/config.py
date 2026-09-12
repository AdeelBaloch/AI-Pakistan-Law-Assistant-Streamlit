import os

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), interpolate=False)

# If ADMIN_PASSWORD is not in .env, reuse the demo value from .env.example.
if not os.getenv("ADMIN_PASSWORD"):
    _example = os.path.join(PROJECT_ROOT, ".env.example")
    if os.path.isfile(_example):
        from dotenv import dotenv_values

        _example_values = dotenv_values(_example, interpolate=False)
        _demo_password = str(_example_values.get("ADMIN_PASSWORD") or "").strip()
        if _demo_password:
            os.environ["ADMIN_PASSWORD"] = _demo_password

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

CHUNKS_FILE = os.path.join(PROJECT_ROOT, "docs", "chunks.json")
EMBEDDINGS_FILE = os.path.join(PROJECT_ROOT, "docs", "embeddings.json")
MANIFEST_FILE = os.path.join(PROJECT_ROOT, "docs", "manifest.json")
PROGRESS_FILE = os.path.join(PROJECT_ROOT, "docs", "ingest_progress.json")
PDFS_DIR = os.path.join(PROJECT_ROOT, "docs", "pdfs")

TOP_K = 8
MIN_SCORE = 0.35
QUESTION_MIN_LENGTH = 8
QUESTION_MAX_LENGTH = 1000
HISTORY_TURNS = 3
MAX_RETRIES = 6
RETRY_BACKOFF_SECONDS = (5, 15, 30, 45, 60, 90)
CHUNK_SIZE = 500
CHUNK_OVERLAP = 75
DEFAULT_DOCUMENT_ID = "constitution-1973"
DEFAULT_DOCUMENT_NAME = (
    "Constitution of the Islamic Republic of Pakistan, 1973"
)
KNOWLEDGE_BASE_NAME = DEFAULT_DOCUMENT_NAME


def _from_streamlit(name):
    try:
        import streamlit as st
    except Exception:
        return ""

    try:
        secrets = st.secrets
    except Exception:
        return ""

    try:
        if name in secrets:
            return str(secrets[name]).strip()
    except Exception:
        pass

    for section in ("api", "general"):
        try:
            if section in secrets and name in secrets[section]:
                return str(secrets[section][name]).strip()
        except Exception:
            continue

    return ""


def setting(name, default=""):
    value = os.getenv(name, "").strip()
    if value:
        return value

    value = _from_streamlit(name)
    if value:
        return value

    return str(default).strip()


def get_gemini_api_key():
    return setting("GEMINI_API_KEY")


def get_gemini_embedding_model():
    return setting("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")


def get_groq_api_key():
    return setting("GROQ_API_KEY")


def get_groq_model():
    return setting("GROQ_MODEL", "openai/gpt-oss-120b")


def get_admin_password():
    return setting("ADMIN_PASSWORD")


def missing_api_keys():
    missing = []
    if not get_gemini_api_key():
        missing.append("GEMINI_API_KEY")
    if not get_groq_api_key():
        missing.append("GROQ_API_KEY")
    return missing


# Kept for older imports; prefer the getters above so Streamlit Secrets
# are read at request time, not only on first import.
GEMINI_API_KEY = get_gemini_api_key()
GEMINI_EMBEDDING_MODEL = get_gemini_embedding_model()
GROQ_API_KEY = get_groq_api_key()
GROQ_MODEL = get_groq_model()
