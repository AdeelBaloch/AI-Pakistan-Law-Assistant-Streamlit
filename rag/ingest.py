import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from rag.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKS_FILE,
    DEFAULT_DOCUMENT_ID,
    DEFAULT_DOCUMENT_NAME,
    EMBEDDINGS_FILE,
    MANIFEST_FILE,
    PDFS_DIR,
    PROGRESS_FILE,
)
from rag.search import generate_embedding, reset_cache

KNOWN_TITLES = {
    "constitution": DEFAULT_DOCUMENT_NAME,
    "ppc": "Pakistan Penal Code, 1860",
    "pakistan penal code": "Pakistan Penal Code, 1860",
    "penal code": "Pakistan Penal Code, 1860",
    "crpc": "Code of Criminal Procedure, 1898",
    "cr.pc": "Code of Criminal Procedure, 1898",
    "criminal procedure": "Code of Criminal Procedure, 1898",
    "cpc": "Code of Civil Procedure, 1908",
    "civil procedure": "Code of Civil Procedure, 1908",
    "qanun": "Qanun-e-Shahadat Order, 1984",
    "qso": "Qanun-e-Shahadat Order, 1984",
    "peca": "Prevention of Electronic Crimes Act, 2016",
    "police": "Police Order, 2002",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "law-document"


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def guess_document_name(filename, override=""):
    if override and override.strip():
        return override.strip()

    stem = Path(filename).stem.lower().replace("_", " ").replace("-", " ")
    for key, title in KNOWN_TITLES.items():
        if key in stem:
            return title

    return Path(filename).stem.replace("_", " ").replace("-", " ").strip().title()


def load_json(path, default):
    if not os.path.exists(path):
        return default

    with open(path, "r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return default


def save_json(path, data, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        if compact:
            json.dump(data, file, ensure_ascii=False)
        else:
            json.dump(data, file, ensure_ascii=False, indent=2)


def load_manifest():
    data = load_json(MANIFEST_FILE, {"documents": []})
    if not isinstance(data, dict):
        data = {"documents": []}
    data.setdefault("documents", [])
    return data


def save_manifest(manifest):
    save_json(MANIFEST_FILE, manifest)


def load_chunk_list():
    data = load_json(CHUNKS_FILE, [])
    return data if isinstance(data, list) else []


def load_embedding_map():
    data = load_json(EMBEDDINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def indexed_documents():
    migrate_legacy_constitution()
    return load_manifest().get("documents", [])


def indexed_law_names():
    names = [item.get("document_name") for item in indexed_documents()]
    names = [name for name in names if name]
    return names or [DEFAULT_DOCUMENT_NAME]


def pending_pdfs():
    os.makedirs(PDFS_DIR, exist_ok=True)
    complete_hashes = {
        item.get("file_hash")
        for item in indexed_documents()
        if item.get("file_hash") and item.get("status", "ready") == "ready"
    }
    pending = []
    for path in sorted(Path(PDFS_DIR).glob("*.pdf")):
        digest = file_hash(str(path))
        if digest not in complete_hashes:
            pending.append({
                "path": str(path),
                "filename": path.name,
                "document_name": guess_document_name(path.name),
            })
    return pending


def clean_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text):
    return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)


def detokenize(tokens):
    text = ""
    for token in tokens:
        if not text:
            text = token
        elif re.match(r"[.,!?;:%)\]}]", token):
            text += token
        elif token in ["'", "’"]:
            text += token
        elif text.endswith(("(", "[", "{", "'", "’")):
            text += token
        else:
            text += " " + token
    return text


def extract_pdf_pages(pdf_path):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    doc = fitz.open(pdf_path)
    pages = []
    for page_number, page in enumerate(doc, start=1):
        text = clean_text(page.get_text("text") or "")
        if text:
            pages.append({"page": page_number, "text": text})
    doc.close()
    return pages


def create_chunks(page_data, start_id=1):
    chunks = []
    chunk_id = start_id

    for page in page_data:
        page_number = page["page"]
        text = clean_text(page["text"])
        if not text:
            continue

        paragraphs = re.split(r"\n\s*\n", text)
        current_tokens = []

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            paragraph_tokens = tokenize(paragraph)

            if len(paragraph_tokens) > CHUNK_SIZE:
                if current_tokens:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "page": page_number,
                        "text": detokenize(current_tokens),
                    })
                    chunk_id += 1
                    current_tokens = current_tokens[-CHUNK_OVERLAP:]

                start = 0
                while start < len(paragraph_tokens):
                    end = start + CHUNK_SIZE
                    chunks.append({
                        "chunk_id": chunk_id,
                        "page": page_number,
                        "text": detokenize(paragraph_tokens[start:end]),
                    })
                    chunk_id += 1
                    start += CHUNK_SIZE - CHUNK_OVERLAP

                current_tokens = []
                continue

            if len(current_tokens) + len(paragraph_tokens) <= CHUNK_SIZE:
                if current_tokens:
                    current_tokens.append("\n\n")
                current_tokens.extend(paragraph_tokens)
            else:
                if current_tokens:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "page": page_number,
                        "text": detokenize(current_tokens),
                    })
                    chunk_id += 1
                overlap_tokens = current_tokens[-CHUNK_OVERLAP:]
                current_tokens = overlap_tokens + paragraph_tokens

        if current_tokens:
            chunks.append({
                "chunk_id": chunk_id,
                "page": page_number,
                "text": detokenize(current_tokens),
            })
            chunk_id += 1

    return chunks


def migrate_legacy_constitution():
    chunks = load_chunk_list()
    if not chunks:
        return

    changed = False
    for chunk in chunks:
        if not chunk.get("document_id"):
            chunk["document_id"] = DEFAULT_DOCUMENT_ID
            changed = True
        if not chunk.get("document_name"):
            chunk["document_name"] = DEFAULT_DOCUMENT_NAME
            changed = True

    if changed:
        save_json(CHUNKS_FILE, chunks)

    manifest = load_manifest()
    already = any(
        item.get("document_id") == DEFAULT_DOCUMENT_ID
        for item in manifest.get("documents", [])
    )
    if not already:
        pages = {
            chunk.get("page")
            for chunk in chunks
            if chunk.get("document_id") == DEFAULT_DOCUMENT_ID
        }
        manifest["documents"].append({
            "document_id": DEFAULT_DOCUMENT_ID,
            "document_name": DEFAULT_DOCUMENT_NAME,
            "source_file": "",
            "file_hash": "",
            "chunk_count": sum(
                1 for chunk in chunks
                if chunk.get("document_id") == DEFAULT_DOCUMENT_ID
            ),
            "page_count": len(pages),
            "indexed_at": _now(),
        })
        save_manifest(manifest)

    if changed:
        reset_cache()


def save_uploaded_pdf(uploaded_file, filename=None):
    os.makedirs(PDFS_DIR, exist_ok=True)
    name = filename or getattr(uploaded_file, "name", "law.pdf")
    name = Path(name).name
    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    path = os.path.join(PDFS_DIR, name)
    with open(path, "wb") as file:
        file.write(uploaded_file.getbuffer())
    return path


def load_progress():
    data = load_json(PROGRESS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_progress(progress):
    save_json(PROGRESS_FILE, progress)


def upsert_manifest(manifest, record):
    manifest["documents"] = [
        item for item in manifest["documents"]
        if item.get("document_id") != record.get("document_id")
        and (
            not record.get("file_hash")
            or item.get("file_hash") != record.get("file_hash")
        )
    ]
    manifest["documents"].append(record)
    save_manifest(manifest)


def index_pdf(pdf_path, document_name="", progress=None):
    migrate_legacy_constitution()

    pdf_path = os.path.abspath(pdf_path)
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    digest = file_hash(pdf_path)
    filename = os.path.basename(pdf_path)
    title = guess_document_name(filename, document_name)
    document_id = _slug(Path(filename).stem)

    manifest = load_manifest()
    existing = next(
        (
            item for item in manifest["documents"]
            if item.get("file_hash") == digest
            and item.get("status", "ready") == "ready"
        ),
        None,
    )
    if existing:
        return {
            "status": "skipped",
            "reason": "already indexed",
            "document": existing,
        }

    def report(message, percent=None):
        if progress:
            progress(message, percent)
        else:
            print(message, flush=True)

    report(f"Reading {filename}...", 5)
    pages = extract_pdf_pages(pdf_path)
    if not pages:
        raise ValueError(f"No extractable text found in {filename}.")

    chunks_data = load_chunk_list()
    embeddings = load_embedding_map()
    progress_state = load_progress()
    saved_state = progress_state.get(digest) or {}

    existing_doc_chunks = [
        chunk for chunk in chunks_data
        if chunk.get("document_id") == document_id
        or chunk.get("source_file") == filename
    ]

    if saved_state.get("start_id"):
        start_id = int(saved_state["start_id"])
        report(f"Resuming {filename} from checkpoint start_id={start_id}...", 12)
    elif existing_doc_chunks:
        start_id = min(int(chunk.get("chunk_id") or 0) for chunk in existing_doc_chunks)
        report(f"Resuming {filename} from saved chunks start_id={start_id}...", 12)
    else:
        start_id = 1
        if chunks_data:
            start_id = max(int(chunk.get("chunk_id") or 0) for chunk in chunks_data) + 1

    report(f"Chunking {len(pages)} pages...", 15)
    rebuilt = create_chunks(pages, start_id=start_id)
    for chunk in rebuilt:
        chunk["document_id"] = document_id
        chunk["document_name"] = title
        chunk["source_file"] = filename
        chunk["file_hash"] = digest

    rebuilt_ids = {str(chunk["chunk_id"]) for chunk in rebuilt}
    chunks_data = [
        chunk for chunk in chunks_data
        if str(chunk.get("chunk_id")) not in rebuilt_ids
        and chunk.get("document_id") != document_id
        and chunk.get("source_file") != filename
    ]
    chunks_data.extend(rebuilt)
    save_json(CHUNKS_FILE, chunks_data)

    total = len(rebuilt)
    already_ids = [
        str(chunk["chunk_id"])
        for chunk in rebuilt
        if str(chunk["chunk_id"]) in embeddings
    ]
    already = len(already_ids)
    report(
        f"Creating embeddings for {total} chunks "
        f"({already} already saved, {total - already} remaining)...",
        20,
    )

    progress_state[digest] = {
        "document_id": document_id,
        "source_file": filename,
        "start_id": start_id,
        "total": total,
        "embedded_count": already,
        "updated_at": _now(),
    }
    save_progress(progress_state)

    upsert_manifest(manifest, {
        "document_id": document_id,
        "document_name": title,
        "source_file": filename,
        "file_hash": digest,
        "chunk_count": total,
        "embedded_count": already,
        "page_count": len(pages),
        "status": "indexing",
        "indexed_at": _now(),
    })

    generated_now = 0
    try:
        for index, chunk in enumerate(rebuilt, start=1):
            chunk_id = str(chunk["chunk_id"])
            percent = 20 + int((index / max(total, 1)) * 75)
            if chunk_id in embeddings:
                report(f"SKIP already saved {index}/{total}", percent)
                continue

            vector = generate_embedding(chunk["text"])
            embeddings[chunk_id] = {
                "chunk_id": chunk["chunk_id"],
                "page": chunk["page"],
                "document_id": document_id,
                "document_name": title,
                "embedding": vector,
            }
            save_json(EMBEDDINGS_FILE, embeddings, compact=True)
            generated_now += 1
            progress_state[digest]["embedded_count"] = already + generated_now
            progress_state[digest]["updated_at"] = _now()
            save_progress(progress_state)
            report(f"NEW embedding {index}/{total}", percent)
            time.sleep(0.2)
    except Exception:
        embedded_count = sum(
            1 for chunk in rebuilt
            if str(chunk["chunk_id"]) in embeddings
        )
        progress_state[digest]["embedded_count"] = embedded_count
        progress_state[digest]["updated_at"] = _now()
        save_progress(progress_state)
        upsert_manifest(manifest, {
            "document_id": document_id,
            "document_name": title,
            "source_file": filename,
            "file_hash": digest,
            "chunk_count": total,
            "embedded_count": embedded_count,
            "page_count": len(pages),
            "status": "indexing",
            "indexed_at": _now(),
        })
        reset_cache()
        raise

    save_json(EMBEDDINGS_FILE, embeddings, compact=True)
    progress_state.pop(digest, None)
    save_progress(progress_state)
    record = {
        "document_id": document_id,
        "document_name": title,
        "source_file": filename,
        "file_hash": digest,
        "chunk_count": total,
        "embedded_count": total,
        "page_count": len(pages),
        "status": "ready",
        "indexed_at": _now(),
    }
    upsert_manifest(manifest, record)
    reset_cache()
    report(f"Indexed {title}", 100)

    return {
        "status": "resumed" if already else "indexed",
        "generated_now": generated_now,
        "skipped": already,
        "document": record,
    }


def index_new_pdfs(progress=None):
    results = []
    pending = pending_pdfs()
    if not pending:
        return results

    for item in pending:
        results.append(
            index_pdf(
                item["path"],
                document_name=item["document_name"],
                progress=progress,
            )
        )
    return results
