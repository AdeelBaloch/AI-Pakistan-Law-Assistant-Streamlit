# PakLaw AI — Streamlit

Pakistan-focused legal information assistant. Users ask questions in English or Urdu. The app retrieves relevant Constitution excerpts with RAG, then answers only from those sources.

This is the Streamlit demo of the existing local PHP project.

## What it does

- Chat interface with follow-up context
- Semantic search over pre-indexed Constitution chunks
- Groq answer generation from retrieved pages
- Source cards with chunk, page, and match score
- Safe reply when the document does not contain the answer

## Knowledge base

Current indexed document:

- Constitution of the Islamic Republic of Pakistan, 1973

## Setup

```bash
cd C:\laragon\www\php_ai_practice\AI-Pakistan-Law-Assistant-Streamlit
python -m pip install -r requirements.txt
```

Create a `.env` file in this folder:

```
GEMINI_API_KEY=your_gemini_api_key
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
```

If `.env` is missing, the app can reuse keys from the sibling PHP project:

`C:\laragon\www\php_ai_practice\AI-Pakistan-Law-Assistant\.env`

## Run the demo

```bash
streamlit run app.py
```

Then open the local URL Streamlit prints, usually `http://localhost:8501`.

## Demo questions

- What is the state religion of Pakistan?
- What does Article 10A say about fair trial?
- Who is the Head of State under the Constitution?
- What are fundamental rights under the Constitution?
- Police mujhe warrant ke baghair kab arrest kar sakti hai?
- Section 144 kya hai?

The last question is useful for showing the safety path: the current knowledge base is the Constitution only, so the assistant should say the point is not found there.

## Disclaimer

PakLaw AI provides legal information for educational and informational purposes only. It does not replace professional legal advice.
