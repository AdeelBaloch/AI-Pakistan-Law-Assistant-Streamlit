import streamlit as st

import re

from rag.assistant import ask_question, validate_question
from rag.config import KNOWLEDGE_BASE_NAME, missing_api_keys
from rag.search import load_chunks, load_embeddings

st.set_page_config(
    page_title="PakLaw AI | Pakistan Law Assistant",
    page_icon="⭐",
    layout="centered",
)

DEMO_QUESTIONS = [
    "What is the state religion of Pakistan?",
    "What does Article 10A say about fair trial?",
    "Who is the Head of State under the Constitution?",
    "What are fundamental rights under the Constitution?",
    "Police mujhe warrant ke baghair kab arrest kar sakti hai?",
    "Section 144 kya hai?",
]

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Noto+Nastaliq+Urdu:wght@500;700&family=Source+Sans+3:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: "Source Sans 3", sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 10%, rgba(201, 162, 39, 0.16), transparent 28%),
            radial-gradient(circle at 90% 0%, rgba(1, 65, 28, 0.18), transparent 32%),
            linear-gradient(180deg, #eef4ee 0%, #f6f1e4 100%);
    }

    [data-testid="stSidebar"] {
        background: #fffdf8;
        border-right: 1px solid rgba(1, 65, 28, 0.14);
    }

    .hero {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin: 8px 0 18px;
    }

    .eyebrow {
        margin: 0 0 4px;
        color: #0d6b38;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        font-size: 12px;
        font-weight: 700;
    }

    .hero h1 {
        margin: 0;
        font-family: "Cormorant Garamond", serif;
        font-size: clamp(32px, 5vw, 46px);
        line-height: 1;
        color: #022613;
    }

    .urdu {
        margin: 8px 0 0;
        font-family: "Noto Nastaliq Urdu", serif;
        font-size: 22px;
        color: #01411c;
    }

    .flag {
        width: 58px;
        height: 58px;
        border-radius: 50%;
        background: #01411c;
        border: 3px solid #c9a227;
        display: grid;
        place-items: center;
        color: #fff;
        font-size: 26px;
        box-shadow: 0 8px 24px rgba(1, 65, 28, 0.25);
        flex-shrink: 0;
    }

    .banner {
        background: linear-gradient(90deg, #022613, #01411c 70%, #0b5a30);
        color: #fff;
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 18px;
        font-size: 14px;
    }

    .banner strong {
        color: #c9a227;
    }

    .disclaimer {
        color: #5c675d;
        font-size: 13px;
        line-height: 1.5;
    }

    .source-card {
        border: 1px solid rgba(1, 65, 28, 0.14);
        border-radius: 12px;
        padding: 10px 12px;
        margin-bottom: 8px;
        background: #fbfaf4;
        font-size: 13px;
    }

    .source-meta {
        color: #01411c;
        font-weight: 700;
        margin-bottom: 4px;
    }

    [data-testid="stChatMessage"] {
        background: #fffdf8;
        border: 1px solid rgba(1, 65, 28, 0.10);
        border-radius: 16px;
    }
</style>
"""


def init_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = ""


def knowledge_stats():
    chunks = load_chunks()
    embeddings = load_embeddings()
    pages = {
        item.get("page")
        for item in chunks.values()
        if item.get("page") is not None
    }
    return len(chunks), len(embeddings), len(pages)


def public_error(error):
    text = str(error or "").strip()
    text = re.sub(r"(gsk_|AQ\.|Bearer |AIza)[^\s\"']+", "[hidden]", text)
    return text[:300]


def render_sources(sources):
    if not sources:
        return

    with st.expander("Document sources", expanded=True):
        for source in sources:
            score = float(source.get("score") or 0)
            preview = (source.get("text") or "").strip()
            st.markdown(
                f"""
                <div class="source-card">
                    <div class="source-meta">
                        Chunk {source.get("chunk_id")} &nbsp;|&nbsp;
                        Page {source.get("page")} &nbsp;|&nbsp;
                        Match {score * 100:.1f}%
                    </div>
                    {preview}
                </div>
                """,
                unsafe_allow_html=True,
            )


def answer_question(question):
    try:
        question = validate_question(question)
    except ValueError as error:
        st.session_state.messages.append({
            "role": "assistant",
            "content": str(error),
            "sources": [],
            "error": True,
        })
        return

    st.session_state.messages.append({"role": "user", "content": question})

    history = [
        message
        for message in st.session_state.messages[:-1]
        if not message.get("error")
    ]

    with st.spinner("Talash ki ja rahi hai..."):
        try:
            result = ask_question(question, history=history)
        except Exception as error:
            detail = public_error(error)
            result = {
                "success": False,
                "message": (
                    "The assistant could not answer right now. Please try again."
                    + (f"\n\nDetail: {detail}" if detail else "")
                ),
                "error": detail,
                "sources": [],
            }

    if result.get("success"):
        st.session_state.messages.append({
            "role": "assistant",
            "content": result.get("answer") or "",
            "sources": result.get("sources") or [],
        })
        return

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("message") or "Jawab hasil nahi ho saka.",
        "sources": result.get("sources") or [],
        "error": True,
    })


def main():
    init_state()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.markdown(
        """
        <div class="hero">
            <div>
                <p class="eyebrow">Islamic Republic of Pakistan</p>
                <h1>Pakistan Law Assistant</h1>
                <p class="urdu">آئین پاکستان معاون</p>
            </div>
            <div class="flag">★</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="banner">
            Source document: <strong>{KNOWLEDGE_BASE_NAME}</strong><br>
            Answers are limited to this document only.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### PakLaw AI")
        st.caption("Pakistan AI Policy & Law Assistant")

        missing = missing_api_keys()
        if missing:
            st.error("API keys missing: " + ", ".join(missing))
            st.caption("Add them in Streamlit Cloud → App settings → Secrets.")
        else:
            st.success("API keys loaded")

        try:
            chunk_count, embedding_count, page_count = knowledge_stats()
            st.success("Knowledge base ready")
            st.markdown(f"**Indexed chunks:** {chunk_count}")
            st.markdown(f"**Pages covered:** {page_count}")
            st.caption(f"{embedding_count} embeddings loaded")
        except Exception as error:
            st.error("Knowledge base could not be loaded.")
            st.caption(str(error))

        st.markdown("### Demo questions")
        for question in DEMO_QUESTIONS:
            if st.button(question, use_container_width=True):
                st.session_state.pending_question = question
                st.rerun()

        if st.button("Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_question = ""
            st.rerun()

        st.markdown("---")
        st.markdown(
            """
            <p class="disclaimer">
                PakLaw AI provides legal information for educational purposes only.
                It does not replace professional legal advice. The system should
                not invent laws, sections, articles or punishments.
            </p>
            """,
            unsafe_allow_html=True,
        )

    if not st.session_state.messages:
        st.info(
            "Apna qanooni sawal English ya Urdu mein likhein. "
            "Assistant Constitution ke indexed pages se jawab dega."
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message.get("content") or "")
            if message["role"] == "assistant":
                render_sources(message.get("sources") or [])

    pending = st.session_state.pending_question
    typed = st.chat_input("Apna qanooni sawal likhein...")

    if pending:
        st.session_state.pending_question = ""
        answer_question(pending)
        st.rerun()
    elif typed:
        answer_question(typed)
        st.rerun()

    st.caption(
        "This assistant searches Constitution chunks, then answers only from those pages. "
        "It is not a substitute for a lawyer or a court."
    )


if __name__ == "__main__":
    main()
