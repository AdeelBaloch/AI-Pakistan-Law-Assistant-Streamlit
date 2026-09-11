import requests

from rag.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    HISTORY_TURNS,
    KNOWLEDGE_BASE_NAME,
    QUESTION_MAX_LENGTH,
    QUESTION_MIN_LENGTH,
)
from rag.search import search


def validate_question(question):
    if not isinstance(question, str):
        raise ValueError("Invalid question.")

    question = " ".join(question.strip().split())

    if question == "":
        raise ValueError("Please enter your legal question.")

    if len(question) < QUESTION_MIN_LENGTH:
        raise ValueError(
            f"Question is too short. Write at least {QUESTION_MIN_LENGTH} characters."
        )

    if len(question) > QUESTION_MAX_LENGTH:
        raise ValueError(
            f"Question is too long. Keep it under {QUESTION_MAX_LENGTH} characters."
        )

    if not any(char.isalpha() for char in question):
        raise ValueError("Please write the question in English or Urdu.")

    return question


def build_search_query(question, history):
    if not history:
        return question

    last_user = ""
    for message in reversed(history):
        if message.get("role") == "user":
            last_user = (message.get("content") or "").strip()
            break

    if not last_user or last_user.lower() == question.lower():
        return question

    return f"{last_user}\n{question}"


def recent_turns(history, limit=HISTORY_TURNS):
    pairs = []
    pending_user = None

    for message in history:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user:
            pairs.append((pending_user, content))
            pending_user = None

    return pairs[-limit:]


def build_law_prompt(question, chunks, history):
    context_parts = []

    for index, chunk in enumerate(chunks, start=1):
        page = chunk.get("page", "N/A")
        text = (chunk.get("text") or "").strip()
        text = text.replace("\u202f", " ").replace("\xa0", " ")
        context_parts.append(f"[Excerpt {index} | Page {page}]\n{text}")

    context = "\n\n".join(context_parts)

    conversation = ""
    turns = recent_turns(history)
    if turns:
        lines = []
        for user_text, assistant_text in turns:
            lines.append(f"User: {user_text}")
            lines.append(f"Assistant: {assistant_text}")
        conversation = "RECENT CONVERSATION:\n" + "\n".join(lines) + "\n\n"

    system_prompt = (
        "You are PakLaw AI, a Pakistan Law Assistant for the "
        f"{KNOWLEDGE_BASE_NAME}.\n\n"
        "Answer only from the constitution excerpts given to you.\n"
        "If the excerpts do not contain the answer, say that this point "
        "is not found in the provided Constitution text.\n"
        "Do not invent articles, amendments, case law, punishments, or outside facts.\n"
        "Cite page numbers from the excerpts when you use them.\n"
        "Write in the same language as the question (English or Urdu).\n"
        "Be formal, clear, and precise.\n"
        "This is not legal advice and you are not a court."
    )

    user_prompt = (
        f"{conversation}"
        "CONSTITUTION EXCERPTS:\n"
        f"{context}\n\n"
        "QUESTION:\n"
        f"{question}\n\n"
        "Answer using only the excerpts above. Use the recent conversation "
        "only to understand follow-up questions, not as a source of law."
    )

    return system_prompt, user_prompt


def call_groq(system_prompt, user_prompt):
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY is missing. Add it to your .env file.")

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
        json={
            "model": GROQ_MODEL,
            "temperature": 0.2,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=120,
    )

    if response.status_code != 200:
        detail = response.text[:240].strip()
        raise Exception(
            f"Groq request failed. HTTP {response.status_code}. {detail}"
        )

    data = response.json()
    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    if not answer or not answer.strip():
        raise Exception("Groq returned an empty answer.")

    return answer.strip()


def ask_question(question, history=None):
    history = history or []
    question = validate_question(question)
    chunks = search(build_search_query(question, history))

    if not chunks:
        return {
            "success": False,
            "message": "No matching text was found in the Constitution document.",
            "sources": [],
        }

    system_prompt, user_prompt = build_law_prompt(question, chunks, history)
    answer = call_groq(system_prompt, user_prompt)

    sources = [
        {
            "chunk_id": chunk.get("chunk_id"),
            "page": chunk.get("page"),
            "score": chunk.get("score"),
            "text": (chunk.get("text") or "")[:280],
        }
        for chunk in chunks
    ]

    return {
        "success": True,
        "answer": answer,
        "sources": sources,
    }
