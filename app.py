import hmac
import html
import re

import streamlit as st

from rag.assistant import ask_question, validate_question
from rag.config import get_admin_password, missing_api_keys
from rag.ingest import (
    index_new_pdfs,
    index_pdf,
    indexed_documents,
    indexed_law_names,
    pending_pdfs,
    save_uploaded_pdf,
)
from rag.search import load_embeddings

st.set_page_config(
    page_title="Pakistan Law AI Assistant",
    page_icon="⭐",
    layout="centered",
)

DEMO_QUESTIONS = [
    "Mere ghar pe kisi bande ne gundo ke sath qabza kiya hai, mujhe kya karna chahiye?",
    "What does Article 10A say about fair trial?",
    "Police mujhe warrant ke baghair kab arrest kar sakti hai?",
    "What are fundamental rights under the Constitution?",
    "What is the state religion of Pakistan?",
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
    if "admin_ok" not in st.session_state:
        st.session_state.admin_ok = False


def knowledge_stats():
    docs = [
        item for item in indexed_documents()
        if item.get("status", "ready") == "ready"
    ]
    chunk_count = sum(int(item.get("chunk_count") or 0) for item in docs)
    page_count = sum(int(item.get("page_count") or 0) for item in docs)
    embedding_count = len(load_embeddings())
    return chunk_count, embedding_count, page_count, docs


def public_error(error):
    text = str(error or "").strip()
    text = re.sub(r"(gsk_|AQ\.|Bearer |AIza)[^\s\"']+", "[hidden]", text)
    return text[:300]


def password_matches(entered):
    expected = get_admin_password()
    if not expected or not entered:
        return False
    try:
        return hmac.compare_digest(entered.encode("utf-8"), expected.encode("utf-8"))
    except Exception:
        return False


def render_admin_panel():
    expected = get_admin_password()
    if not expected:
        st.caption(
            "Upload sirf admin ke liye hai. Streamlit Secrets ya .env mein "
            "ADMIN_PASSWORD set karo. Local indexing: python ingest_laws.py"
        )
        return

    if not st.session_state.admin_ok:
        entered = st.text_input("Admin password", type="password")
        if st.button("Unlock admin", use_container_width=True):
            if password_matches(entered):
                st.session_state.admin_ok = True
                st.rerun()
            st.error("Galat password.")
        return

    st.success("Admin mode")
    st.caption("PPC, CrPC ya koi aur PDF yahan upload karo. Constitution dubara process nahi hogi.")
    uploaded = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")
    custom_name = st.text_input(
        "Law name (optional)",
        placeholder="Pakistan Penal Code, 1860",
    )
    if st.button("Save and index PDF", use_container_width=True, disabled=uploaded is None):
        if uploaded is None:
            st.warning("Pehle PDF choose karo.")
        else:
            saved_path = save_uploaded_pdf(uploaded)
            status = st.empty()
            bar = st.progress(0)

            def report(message, percent=None):
                status.write(message)
                if percent is not None:
                    bar.progress(min(max(int(percent), 0), 100))

            try:
                result = index_pdf(
                    saved_path,
                    document_name=custom_name,
                    progress=report,
                )
                if result.get("status") == "skipped":
                    st.info("Ye PDF pehle se indexed hai.")
                else:
                    doc = result.get("document") or {}
                    st.success(
                        f"Indexed: {doc.get('document_name')} "
                        f"({doc.get('chunk_count')} chunks)"
                    )
                st.rerun()
            except Exception as error:
                st.error(public_error(error))

    waiting = pending_pdfs()
    if waiting:
        st.caption("docs/pdfs mein new files: " + ", ".join(item["filename"] for item in waiting))
        if st.button("Index pending PDFs", use_container_width=True):
            status = st.empty()
            bar = st.progress(0)

            def report(message, percent=None):
                status.write(message)
                if percent is not None:
                    bar.progress(min(max(int(percent), 0), 100))

            try:
                results = index_new_pdfs(progress=report)
                st.success(f"{len(results)} document(s) processed.")
                st.rerun()
            except Exception as error:
                st.error(public_error(error))

    if st.button("Lock admin", use_container_width=True):
        st.session_state.admin_ok = False
        st.rerun()


def knowledge_label():
    names = indexed_law_names()
    return " + ".join(names)


def render_sources(sources):
    if not sources:
        return

    with st.expander("Document sources", expanded=False):
        for source in sources:
            score = float(source.get("score") or 0)
            preview = html.escape((source.get("text") or "").strip())
            law = html.escape(source.get("document_name") or "Indexed law")
            st.markdown(
                f"""
                <div class="source-card">
                    <div class="source-meta">
                        {law} &nbsp;|&nbsp;
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
    raw_question = question if isinstance(question, str) else ""
    st.session_state.messages.append({
        "role": "user",
        "content": " ".join(raw_question.strip().split()),
    })

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
                <h1>Pakistan Law AI Assistant</h1>
                <p class="urdu">پاکستان قانون معاون</p>
            </div>
            <div class="flag">★</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="banner">
            Indexed laws: <strong>{html.escape(knowledge_label())}</strong><br>
            Answers come only from these indexed documents.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### Pakistan Law AI Assistant")
        st.caption("Pakistan-focused legal information assistant")

        missing = missing_api_keys()
        if missing:
            st.error("API keys missing: " + ", ".join(missing))
            st.caption("Add them in Streamlit Cloud → App settings → Secrets.")
        else:
            st.success("API keys loaded")

        try:
            chunk_count, embedding_count, page_count, docs = knowledge_stats()
            st.success("Knowledge base ready")
            st.markdown(f"**Indexed chunks:** {chunk_count}")
            st.markdown(f"**Pages covered:** {page_count}")
            st.caption(f"{embedding_count} embeddings loaded")
            for item in docs:
                st.caption(
                    f"• {item.get('document_name')} "
                    f"({item.get('chunk_count')} chunks, {item.get('page_count')} pages)"
                )
        except Exception as error:
            st.error("Knowledge base could not be loaded.")
            st.caption(str(error))

        with st.expander("Admin"):
            render_admin_panel()

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
                Pakistan Law AI Assistant provides legal information for educational purposes only.
                It does not replace professional legal advice. The system should
                not invent laws, sections, articles or punishments.
            </p>
            """,
            unsafe_allow_html=True,
        )

    if not st.session_state.messages:
        st.info(
            "Apna qanooni sawal English ya Urdu mein likhein. "
            "Assistant indexed Pakistani laws se jawab dega."
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message.get("content") or "")
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
        "This assistant searches indexed law chunks, then answers only from those pages. "
        "It is not a substitute for a lawyer or a court."
    )


if __name__ == "__main__":
    main()
