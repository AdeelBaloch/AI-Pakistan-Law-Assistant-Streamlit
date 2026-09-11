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


def load_chunks():
    global _CHUNKS

    if _CHUNKS is None:
        with open(CHUNKS_FILE, "r", encoding="utf-8") as file:
            chunks = json.load(file)
        _CHUNKS = {str(chunk["chunk_id"]): chunk for chunk in chunks}

    return _CHUNKS


def load_embeddings():
    global _EMBEDDINGS

    if _EMBEDDINGS is None:
        if not os.path.exists(EMBEDDINGS_FILE):
            raise Exception(f"Embeddings file not found: {EMBEDDINGS_FILE}")

        with open(EMBEDDINGS_FILE, "r", encoding="utf-8") as file:
            _EMBEDDINGS = json.load(file)

    return _EMBEDDINGS


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
        response = requests.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code == 200:
            return response.json()["embedding"]["values"]

        last_error = f"Embedding failed. HTTP {response.status_code}"
        print("Gemini API Error:", file=sys.stderr)
        print(response.text, file=sys.stderr)

        if response.status_code == 429 and attempt < MAX_RETRIES:
            wait_seconds = RETRY_BACKOFF_SECONDS[attempt]
            print(
                f"Rate limited (429). Waiting {wait_seconds} sec then retry "
                f"{attempt + 1}/{MAX_RETRIES}...",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)
            continue

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
        })

    return results
