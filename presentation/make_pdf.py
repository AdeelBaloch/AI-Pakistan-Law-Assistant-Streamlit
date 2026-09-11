"""Build a lightweight 16:9 presentation PDF (no Chrome/HTML layers)."""

import math
from pathlib import Path

import pymupdf

OUT = Path(__file__).with_name("Pakistan-Law-AI-Assistant.pdf")
FONTS = Path(r"C:\Windows\Fonts")

W, H = 960, 540  # 16:9, PowerPoint widescreen
GREEN = (0.004, 0.255, 0.110)
DEEP = (0.008, 0.149, 0.075)
GOLD = (0.788, 0.635, 0.153)
BG = (0.933, 0.957, 0.933)
PAPER = (1.0, 0.992, 0.973)
INK = (0.106, 0.141, 0.110)
MUTED = (0.361, 0.404, 0.365)
WHITE = (1, 1, 1)

TITLE_FONT = str(FONTS / "georgiab.ttf")
BODY_FONT = str(FONTS / "segoeui.ttf")
BODY_BOLD = str(FONTS / "segoeuib.ttf")


def draw_star(page, cx, cy, r_out=9, r_in=3.8):
    points = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        radius = r_out if i % 2 == 0 else r_in
        points.append(pymupdf.Point(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    shape = page.new_shape()
    shape.draw_polyline(points)
    shape.finish(color=GOLD, fill=GOLD, closePath=True, width=0)
    shape.commit()


def banner(page, title):
    r = pymupdf.Rect(28, 22, W - 28, 88)
    page.draw_rect(r, color=DEEP, fill=DEEP, width=0)
    accent = pymupdf.Rect(28, 22, W - 28, 26)
    page.draw_rect(accent, color=GOLD, fill=GOLD, width=0)
    page.insert_text(
        (48, 64),
        title,
        fontfile=TITLE_FONT,
        fontsize=28,
        color=GOLD,
    )
    cx, cy = W - 66, 55
    page.draw_circle(pymupdf.Point(cx, cy), 18, color=GOLD, fill=DEEP, width=2.2)
    draw_star(page, cx, cy)


def heading(page, text, y=118):
    page.insert_text((40, y), text, fontfile=TITLE_FONT, fontsize=26, color=DEEP)
    return y + 28


def wrap_lines(text, fontfile, size, max_width):
    font = pymupdf.Font(fontfile=fontfile)
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if font.text_length(trial, fontsize=size) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def paragraph(page, text, y, size=16, color=INK, width=W - 80, fontfile=BODY_FONT, leading=None):
    leading = leading or size + 7
    for line in wrap_lines(text, fontfile, size, width):
        page.insert_text((40, y), line, fontfile=fontfile, fontsize=size, color=color)
        y += leading
    return y


def paragraph_at(page, text, x, y, size=16, color=INK, width=700, fontfile=BODY_FONT, leading=None):
    leading = leading or size + 7
    for line in wrap_lines(text, fontfile, size, width):
        page.insert_text((x, y), line, fontfile=fontfile, fontsize=size, color=color)
        y += leading
    return y


def bullets_at(page, items, y, size=16.5):
    for item in items:
        page.draw_circle((52, y - 5), 3.2, color=GOLD, fill=GOLD, width=0)
        y = paragraph_at(page, item, 68, y, size=size, width=W - 120)
        y += 12
    return y


def card(page, rect, title, body):
    page.draw_rect(rect, color=(0.75, 0.82, 0.76), fill=PAPER, width=0.6)
    page.insert_text(
        (rect.x0 + 16, rect.y0 + 32),
        title,
        fontfile=BODY_BOLD,
        fontsize=16,
        color=GREEN,
    )
    paragraph_at(page, body, rect.x0 + 16, rect.y0 + 56, size=13.5, color=INK, width=rect.width - 32)


def pill(page, x, y, text):
    font = pymupdf.Font(fontfile=BODY_BOLD)
    tw = font.text_length(text, fontsize=12)
    r = pymupdf.Rect(x, y, x + tw + 24, y + 28)
    page.draw_rect(r, color=(0.75, 0.82, 0.76), fill=WHITE, width=0.7)
    page.insert_text((x + 12, y + 19), text, fontfile=BODY_BOLD, fontsize=12, color=GREEN)
    return r.x1


def new_page(doc):
    page = doc.new_page(width=W, height=H)
    page.draw_rect(page.rect, color=BG, fill=BG, width=0)
    page.draw_rect(pymupdf.Rect(0, H - 8, W, H), color=GREEN, fill=GREEN, width=0)
    return page


def footer(page, n):
    page.insert_text(
        (W - 70, H - 22),
        f"{n} / 6",
        fontfile=BODY_FONT,
        fontsize=11,
        color=MUTED,
    )


def build():
    doc = pymupdf.open()

    # 1. Title
    page = new_page(doc)
    banner(page, "Pakistan Law AI Assistant")
    y = heading(page, "Pakistani law. Simple questions.")
    y = paragraph(
        page,
        "Users ask in English, Urdu, or Roman Urdu. The app retrieves relevant pages from indexed Pakistani law books, then answers with sources.",
        y + 8,
        size=16.5,
    )
    card(page, pymupdf.Rect(40, 290, 460, 400), "1,369 chunks", "4 law books indexed")
    card(page, pymupdf.Rect(480, 290, 920, 400), "732 pages", "Constitution, PPC, CrPC, Family Laws")
    page.insert_text((40, 450), "2-3 minute demo pitch", fontfile=BODY_FONT, fontsize=13, color=MUTED)
    footer(page, 1)

    # 2. Problem
    page = new_page(doc)
    banner(page, "The problem")
    y = heading(page, "The law is long. The question is simple.")
    bullets_at(
        page,
        [
            "Pakistani statutes are lengthy - finding the right article or section takes time.",
            'People ask in everyday language: "Someone occupied my house. What should I do?"',
            "A general web search rarely returns the exact document, section, and page.",
        ],
        y + 24,
        size=17,
    )
    footer(page, 2)

    # 3. Solution
    page = new_page(doc)
    banner(page, "The solution")
    y = heading(page, "A RAG chatbot - it retrieves, it does not invent.")
    x = 40
    y = 170
    for label, last in [
        ("PDF laws", False),
        ("Chunks + embeddings", False),
        ("Semantic search", False),
        ("LLM answer + sources", True),
    ]:
        x = pill(page, x, y, label)
        if not last:
            page.insert_text((x + 6, y + 19), ">", fontfile=BODY_BOLD, fontsize=14, color=GOLD)
            x += 26
    card(page, pymupdf.Rect(40, 250, 460, 380), "Gemini", "Query embeddings (768-d)")
    card(page, pymupdf.Rect(480, 250, 920, 380), "Groq", "Answers only from retrieved text")
    footer(page, 3)

    # 4. Law books
    page = new_page(doc)
    banner(page, "Law books")
    y = heading(page, "What is indexed today")
    y = bullets_at(
        page,
        [
            "Constitution of Pakistan, 1973 - 326 chunks, 240 pages",
            "Pakistan Penal Code, 1860 - 328 chunks, 178 pages",
            "Code of Criminal Procedure, 1898 - 703 chunks, 307 pages",
            "Muslim Family Laws Ordinance - 12 chunks, 7 pages",
        ],
        y + 16,
        size=16.5,
    )
    paragraph(
        page,
        "Adding a new book is dynamic: an admin uploads a PDF, and chunks plus embeddings are created. Already indexed laws are not processed again.",
        y + 8,
        size=15,
    )
    footer(page, 4)

    # 5. Demo
    page = new_page(doc)
    banner(page, "Live demo")
    y = heading(page, "Three questions, 60 seconds")
    boxes = [
        ("1.", "What are fundamental rights under the Constitution?"),
        ("2.", "Someone occupied my house with armed men. What should I do?"),
        ("3.", "What is Section 144?  - answered from CrPC, with sources"),
    ]
    top = 168
    for i, (num, text) in enumerate(boxes):
        r = pymupdf.Rect(40, top + i * 78, 920, top + 66 + i * 78)
        page.draw_rect(r, color=(0.75, 0.82, 0.76), fill=PAPER, width=0.6)
        page.insert_text((r.x0 + 16, r.y0 + 40), num, fontfile=BODY_BOLD, fontsize=18, color=GREEN)
        page.insert_text((r.x0 + 48, r.y0 + 40), text, fontfile=BODY_FONT, fontsize=15.5, color=INK)
    page.insert_text(
        (40, 430),
        "Answers are point-by-point, with article or section citations. Sources show the law name, page, and match score.",
        fontfile=BODY_FONT,
        fontsize=13,
        color=MUTED,
    )
    footer(page, 5)

    # 6. Close
    page = new_page(doc)
    banner(page, "Safety and close")
    y = heading(page, "This is not a lawyer. It is information from indexed books.")
    y = bullets_at(
        page,
        [
            "If a section or punishment is not in the index, the system must not invent it.",
            "Random or meaningless input is rejected.",
            "PDF upload is admin-only.",
        ],
        y + 22,
        size=17,
    )
    page.insert_text(
        (40, 430),
        "Pakistan Law AI Assistant - Pakistani laws, searchable in your language, with sources.",
        fontfile=BODY_BOLD,
        fontsize=15,
        color=GREEN,
    )
    footer(page, 6)

    doc.save(OUT, garbage=4, deflate=True, clean=True)
    doc.close()
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
    print("bytes", path.stat().st_size)
