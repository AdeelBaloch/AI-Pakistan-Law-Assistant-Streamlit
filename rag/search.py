import json
import os
import sys
import time

import requests

from rag.config import (
    CHUNKS_FILE,
    EMBEDDINGS_FILE,
    MAX_RETRIES,
    MIN_SCORE,
    RETRY_BACKOFF_SECONDS,
    TOP_K,
    get_gemini_api_key,
    get_gemini_embedding_model,
)
from rag.similarity import rank_by_similarity

_CHUNKS = None
_EMBEDDINGS = None
_CHUNKS_MTIME = None
_EMBEDDINGS_MTIME = None


def reset_cache():
    global _CHUNKS, _EMBEDDINGS, _CHUNKS_MTIME, _EMBEDDINGS_MTIME
    _CHUNKS = None
    _EMBEDDINGS = None
    _CHUNKS_MTIME = None
    _EMBEDDINGS_MTIME = None


def _file_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def load_chunks():
    global _CHUNKS, _CHUNKS_MTIME

    mtime = _file_mtime(CHUNKS_FILE)
    if _CHUNKS is None or _CHUNKS_MTIME != mtime:
        with open(CHUNKS_FILE, "r", encoding="utf-8") as file:
            chunks = json.load(file)
        _CHUNKS = {str(chunk["chunk_id"]): chunk for chunk in chunks}
        _CHUNKS_MTIME = mtime

    return _CHUNKS


def load_embeddings():
    global _EMBEDDINGS, _EMBEDDINGS_MTIME

    mtime = _file_mtime(EMBEDDINGS_FILE)
    if _EMBEDDINGS is None or _EMBEDDINGS_MTIME != mtime:
        if not os.path.exists(EMBEDDINGS_FILE):
            raise Exception(f"Embeddings file not found: {EMBEDDINGS_FILE}")

        with open(EMBEDDINGS_FILE, "r", encoding="utf-8") as file:
            _EMBEDDINGS = json.load(file)
        _EMBEDDINGS_MTIME = mtime

    return _EMBEDDINGS


def _retry_wait_seconds(response, fallback):
    try:
        payload = response.json()
    except Exception:
        return fallback

    error = payload.get("error") or {}
    for item in error.get("details") or []:
        delay = str((item or {}).get("retryDelay") or "").strip().rstrip("s")
        if delay:
            try:
                return min(max(int(float(delay)) + 1, 1), 120)
            except ValueError:
                continue

    return fallback


def generate_embedding(text):
    api_key = get_gemini_api_key()
    model = get_gemini_embedding_model()

    if not api_key:
        raise Exception(
            "GEMINI_API_KEY is missing. Add it in Streamlit Secrets or a local .env file."
        )

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:embedContent"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "model": f"models/{model}",
        "content": {"parts": [{"text": text}]},
        "output_dimensionality": 768,
    }

    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
        except requests.RequestException as error:
            last_error = f"Network error: {error}"
            print(last_error, file=sys.stderr)
            if attempt < MAX_RETRIES:
                wait_seconds = RETRY_BACKOFF_SECONDS[
                    min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)
                ]
                print(
                    f"Waiting {wait_seconds} sec then retry "
                    f"{attempt + 1}/{MAX_RETRIES}...",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)
                continue
            raise Exception(
                "Internet/DNS failed while calling Gemini. Already-saved chunks "
                "will be skipped on the next run. Check your connection and run ingest again."
            )

        if response.status_code == 200:
            return response.json()["embedding"]["values"]

        last_error = f"Embedding failed. HTTP {response.status_code}"
        print("Gemini API Error:", file=sys.stderr)
        print(response.text, file=sys.stderr)

        if response.status_code == 429 and attempt < MAX_RETRIES:
            fallback = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
            wait_seconds = _retry_wait_seconds(response, fallback)
            print(
                f"Rate limited (429). Waiting {wait_seconds} sec then retry "
                f"{attempt + 1}/{MAX_RETRIES}...",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)
            continue

        if response.status_code == 429:
            raise Exception(
                "Gemini embedding quota/rate limit reached. Already-saved chunks "
                "will be skipped on the next run. Wait and run ingest again to resume."
            )

        raise Exception(last_error)

    raise Exception(last_error)


def search(query, top_k=TOP_K, min_score=MIN_SCORE):
    chunks = load_chunks()
    embeddings = load_embeddings()
    query_vector = generate_embedding(query.strip())
    ranked = rank_by_similarity(query_vector, embeddings)

    results = []
    for item in ranked[:top_k]:
        if item["score"] < min_score:
            continue

        chunk_id = str(item["chunk_id"])
        chunk = chunks.get(chunk_id, {})
        results.append({
            "chunk_id": item["chunk_id"],
            "page": item["page"],
            "score": item["score"],
            "text": chunk.get("text", ""),
            "document_id": chunk.get("document_id", ""),
            "document_name": chunk.get("document_name", ""),
            "source_file": chunk.get("source_file", ""),
        })

    return results
