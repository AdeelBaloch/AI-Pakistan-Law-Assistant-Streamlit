import re
from collections import Counter

import requests

from rag.config import (
    HISTORY_TURNS,
    QUESTION_MAX_LENGTH,
    QUESTION_MIN_LENGTH,
    get_groq_api_key,
    get_groq_model,
)
from rag.search import search

INVALID_QUESTION_MESSAGE = (
    "Yeh koi proper qanooni sawal nahi lagta. "
    "English ya Urdu/Roman Urdu mein clear sawal likhein, "
    "jaise: Section 144 kya hai? ya Article 10A ke baare mein batao."
)
OFF_TOPIC_MESSAGE = (
    "Yeh Pakistan Law AI Assistant hai, hisab ya general sawalon ka jawab "
    "yahan nahi milta. Koi qanooni sawal poochhein, jaise: Section 144 kya hai?"
)
KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
LEGAL_HINTS = (
    "section", "article", "dafa", "qanoon", "qanun", "law", "ppc", "crpc",
    "constitution", "fir", "police", "court", "adalat", "saza", "qaid",
    "arrest", "warrant", "nikah", "talaq", "qabza", "ghar", "zameen",
    "shadi", "biwi", "shohar", "penal", "ordinance", "ain", "jail",
    "jurmana", "fine", "chori", "murder", "zina", "rights", "haq",
    "fundamental", "crpc", "ppc", "family", "property", "makan",
)
ARITHMETIC_HINTS = re.compile(
    r"kitn[aeiy]+\s*(hue|hote|hain|hota|ho[ae]|huwe)|"
    r"\b(plus|minus|add|sum|total|jama|times|multiply|divide|minus)\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"(?:\d|[\u06F0-\u06F9])+")
NON_LEGAL_REPLY_RE = re.compile(
    r"معذرت|صرف قانونی|قانونی سوال|قانونی استفسار|"
    r"only (?:answer|handle) legal|not a legal question|"
    r"qanooni sawal|hisab ya general|"
    r"I (?:can|could) only (?:answer|provide)|"
    r"do not answer (?:non-)?legal|"
    r"testing purpose",
    re.IGNORECASE,
)


def _wild_casing(word):
    if len(word) < 6:
        return False
    flips = 0
    for first, second in zip(word, word[1:]):
        if first.isalpha() and second.isalpha() and first.isupper() != second.isupper():
            flips += 1
    return flips >= 3


def _is_keyboard_smash(word):
    lowered = word.lower()
    return any(lowered in row or row in lowered for row in KEYBOARD_ROWS)


def has_legal_hint(question):
    text = question.lower()
    if re.search(r"\b(section|article|dafa)\s*\d", text, re.IGNORECASE):
        return True
    if re.search(r"\b\d+[a-z]\b", text, re.IGNORECASE):
        return True
    return any(hint in text for hint in LEGAL_HINTS)


def looks_like_arithmetic(question):
    if has_legal_hint(question):
        return False
    if re.search(r"(?:\d|[\u06F0-\u06F9])+\s*[+\-x×*/]\s*(?:\d|[\u06F0-\u06F9])+", question):
        return True
    numbers = NUMBER_RE.findall(question)
    if len(numbers) >= 2 and ARITHMETIC_HINTS.search(question):
        return True
    if len(numbers) >= 2 and re.search(r"kitn[aeiy]+", question, re.IGNORECASE):
        return True
    return False


def is_non_legal_reply(answer):
    return bool(NON_LEGAL_REPLY_RE.search(answer or ""))


def looks_like_real_question(question):
    urdu_chars = len(re.findall(r"[\u0600-\u06FF]", question))
    if urdu_chars >= 6:
        return True

    letters = sum(char.isalpha() for char in question)
    punctuation = sum(
        (not char.isalnum() and not char.isspace())
        for char in question
    )
    if letters and punctuation / max(len(question), 1) > 0.25:
        return False

    tokens = re.findall(r"[A-Za-z]+|[\u0600-\u06FF]+", question)
    tokens = [token for token in tokens if len(token) >= 2]
    if len(tokens) < 2:
        return False

    lowered = [token.lower() for token in tokens]
    most_common_count = Counter(lowered).most_common(1)[0][1]
    if most_common_count >= 3 and most_common_count / len(lowered) >= 0.5:
        return False

    latin_words = [token for token in tokens if re.fullmatch(r"[A-Za-z]+", token)]
    if latin_words:
        with_vowel = sum(
            1 for word in latin_words
            if re.search(r"[aeiouAEIOU]", word)
        )
        if with_vowel / len(latin_words) < 0.4:
            return False
        smash_count = sum(1 for word in latin_words if _is_keyboard_smash(word))
        if smash_count and smash_count / len(latin_words) >= 0.5:
            return False
        if sum(_wild_casing(word) for word in latin_words) >= 1 and with_vowel <= 1:
            return False

    return True


def repair_mixed_script(text):
    """Keep English terms whole so Urdu RTL sentences do not start mid-word."""
    replacements = (
        (r"آرbitration\s*Council", "Arbitration Council"),
        (r"آرbitration", "Arbitration"),
        (r"آرbitrator", "Arbitrator"),
        (r"کنstitution", "Constitution"),
        (r"سیکtion", "Section"),
        (r"آرticle", "Article"),
    )
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = re.sub(r"([\u0600-\u06FF])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z])([\u0600-\u06FF])", r"\1 \2", text)
    return re.sub(r"[ \t]{2,}", " ", text)


MUKHTASAR_HEADING_RE = re.compile(
    r"^(?:\*\*|###|#)?\s*[\u200e\u200f\u2066\u2067\u2068\u2069]*"
    r"(Mukhtas[ae]r\s+jawab|Brief\s+answer|مختصر\s*جواب)"
    r"[\u200e\u200f\u2066\u2067\u2068\u2069]*\s*(?:\*\*)?\s*[:：\-—–]?\s*",
    re.IGNORECASE,
)


def split_mukhtasar_heading(text):
    stripped = (text or "").lstrip()
    match = MUKHTASAR_HEADING_RE.match(stripped)
    if not match:
        return False, text or ""
    rest = stripped[match.end():].lstrip(" \t\r")
    rest = rest.lstrip("\n")
    return True, rest


def format_mukhtasar_heading(text):
    """Force 'Mukhtasar jawab :' on its own line, answer on the next line."""
    found, rest = split_mukhtasar_heading(text)
    if not found:
        return text
    return "Mukhtasar jawab :\n" + rest


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

    if not looks_like_real_question(question):
        raise ValueError(INVALID_QUESTION_MESSAGE)

    if looks_like_arithmetic(question):
        raise ValueError(OFF_TOPIC_MESSAGE)

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
        "- Sound calm, respectful, and clear — like a careful legal information guide, "
        "not a textbook and not casual street talk.\n"
        "- Never write citations like [Excerpt 1 | Page 27]. Cite the law name plus "
        "Article or Section number, for example Constitution Article 24 or PPC Section 448.\n"
        "- Do not use informal labels such as 'Seedha jawab'. Use courteous headings.\n"
        "- URDU SCRIPT RULES: If the reply is in Urdu (Arabic script), write complete "
        "Urdu sentences. Never split an English word across two scripts "
        "(wrong: آرbitration Council). Either keep the full English term in Latin letters "
        "as one unit (Arbitration Council, Section 6, PPC) or use a complete Urdu phrase "
        "(ثالثی کونسل). Do not place English in the middle of an Urdu word.\n\n"
        "ANSWER SHAPE\n"
        "Keep the respectful wording. Always use this structure:\n"
        "1) Start exactly like this, heading on its own line, answer on the next line:\n"
        "   Mukhtasar jawab :\n"
        "   <one or two respectful lines, never on the same line as the heading>\n"
        "   Do not write 'Mukhtasar jawab: text'. After the colon, always press Enter.\n"
        "2) A GitHub-style markdown TABLE of the cited law. Required columns:\n"
        "   | Section / Article | Reference book | Details |\n"
        "   Section / Article = exact number, e.g. Section 6 or Article 24.\n"
        "   Reference book = full law name, e.g. Muslim Family Laws Ordinance "
        "or Pakistan Penal Code, 1860.\n"
        "   Details = what that provision says, in simple words, including "
        "punishment only if it is in the excerpts.\n"
        "   One row per provision. Never invent a row. If a point is not in "
        "the excerpts, omit that row.\n"
        "3) Practical next steps / Aghla iqdamat — only if the user described "
        "a real situation, and only from the excerpts.\n"
        "4) Important note — this is general legal information, not a court "
        "judgment and not a substitute for a lawyer.\n\n"
        "If the user asks about a specific article or section, still start with "
        "the brief answer, then the same table for that provision.\n\n"
        "RULES\n"
        "- Use only the excerpts. Do not invent articles, sections, amendments, "
        "case law, charges, or punishments.\n"
        "- If the excerpts do not cover the point, say so plainly.\n"
        "- If the user asks arithmetic, riddles, or anything that is not Pakistani law, "
        "do not interpret numbers as punishments or sections. Say you only answer legal questions.\n"
        "- Keep it attractive: brief answer, then the markdown table, then next "
        "steps. Do not collapse the answer into one paragraph. Always include "
        "the table when any section or article is cited."
    )

    user_prompt = (
        f"{conversation}"
        "LAW EXCERPTS:\n"
        f"{context}\n\n"
        "QUESTION:\n"
        f"{question}\n\n"
        "Write a practical answer from these excerpts only. "
        "Start with this heading on its own line:\n"
        "Mukhtasar jawab :\n"
        "Then put the brief answer on the next line. "
        "Then a markdown table with columns "
        "Section / Article, Reference book, and Details. "
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

    return format_mukhtasar_heading(repair_mixed_script(answer.strip()))


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
    if is_non_legal_reply(answer):
        sources = []

    return {
        "success": True,
        "answer": answer,
        "sources": sources,
    }
