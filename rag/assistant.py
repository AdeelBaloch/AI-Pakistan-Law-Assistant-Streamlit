import requests

from rag.config import (
    HISTORY_TURNS,
    QUESTION_MAX_LENGTH,
    QUESTION_MIN_LENGTH,
    get_groq_api_key,
    get_groq_model,
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


def expand_search_query(question):
    text = question.lower()
    extras = []

    if any(word in text for word in (
        "qabza", "kamza", "kabza", "ghar", "zameen", "property", "makan",
    )):
        extras.append(
            "protection of property rights Article 23 Article 24 "
            "security of person Article 9 criminal trespass house-trespass "
            "illegal dispossession Pakistan Penal Code Section 441 442 447 448"
        )

    if any(word in text for word in (
        "gunda", "gundo", "dhamki", "maar", "marpeet", "attack", "arrest",
        "police", "warrant",
    )):
        extras.append(
            "security of person Article 9 safeguards as to arrest and detention "
            "Article 10 fair trial Article 10A dignity of man Article 14"
        )

    if any(word in text for word in ("saza", "punishment", "charge", "jurm", "crime")):
        extras.append(
            "Pakistan Penal Code punishment imprisonment fine section "
            "to be dealt with in accordance with law Article 4"
        )

    if extras:
        return question + "\n" + " ".join(extras)

    return question


def build_search_query(question, history):
    query = expand_search_query(question)

    if not history:
        return query

    last_user = ""
    for message in reversed(history):
        if message.get("role") == "user":
            last_user = (message.get("content") or "").strip()
            break

    if not last_user or last_user.lower() == question.lower():
        return query

    return f"{last_user}\n{query}"


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
        law = chunk.get("document_name") or "Pakistani law"
        text = (chunk.get("text") or "").strip()
        text = text.replace("\u202f", " ").replace("\xa0", " ")
        context_parts.append(
            f"[Source {index} | {law} | Page {page}]\n{text}"
        )

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
        "You are Pakistan Law AI Assistant, a practical Pakistan legal information assistant. "
        "Your only sources are the Pakistani law excerpts provided to you "
        "(Constitution, PPC, CrPC, or any other indexed law).\n\n"
        "VOICE AND LANGUAGE\n"
        "- Reply in the same language as the user: English, Urdu, or Roman Urdu.\n"
        "- Sound like a clear, helpful Pakistani explainer, not a textbook.\n"
        "- Never write citations like [Excerpt 1 | Page 27]. Cite the law name plus "
        "Article or Section number, for example Constitution Article 24 or PPC Section 448.\n\n"
        "ANSWER SHAPE\n"
        "If the user describes a real situation (qabza, gunda, arrest, crime, property), use:\n"
        "1) Seedha jawab — 1 or 2 lines.\n"
        "2) Related law — name the article/section and what it means in simple words.\n"
        "3) Point by point — possible charges, what the other person may face, and "
        "what the user can do next, but ONLY if those sections and punishments are "
        "actually in the excerpts.\n"
        "4) Limit — if a charge or jail term is not in the excerpts, say that this "
        "point is not in the currently indexed documents. Do not guess years or sections.\n"
        "5) Short reminder — this is information, not a court judgment or lawyer advice.\n\n"
        "If the user asks about a specific article or section, explain THAT provision:\n"
        "- Title in simple words\n"
        "- What it gives or requires\n"
        "- When it applies in daily life\n"
        "- Punishment or limit if the excerpt states it\n\n"
        "RULES\n"
        "- Use only the excerpts. Do not invent articles, sections, amendments, "
        "case law, charges, or punishments.\n"
        "- If the excerpts do not cover the point, say so plainly.\n"
        "- Keep it attractive: short headings, numbered points, bold article/section names."
    )

    user_prompt = (
        f"{conversation}"
        "LAW EXCERPTS:\n"
        f"{context}\n\n"
        "QUESTION:\n"
        f"{question}\n\n"
        "Write a practical, point-by-point answer from these excerpts only. "
        "Cite law name + Article/Section, not excerpt labels. "
        "Use the recent conversation only to understand follow-ups, not as a source of law."
    )

    return system_prompt, user_prompt


def call_groq(system_prompt, user_prompt):
    api_key = get_groq_api_key()
    model = get_groq_model()

    if not api_key:
        raise Exception(
            "GROQ_API_KEY is missing. Add it in Streamlit Secrets or a local .env file."
        )

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": model,
            "temperature": 0.35,
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
            "message": "No matching text was found in the indexed law documents.",
            "sources": [],
        }

    system_prompt, user_prompt = build_law_prompt(question, chunks, history)
    answer = call_groq(system_prompt, user_prompt)

    sources = [
        {
            "document_name": chunk.get("document_name") or "",
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
