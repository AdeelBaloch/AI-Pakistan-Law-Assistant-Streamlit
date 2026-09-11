from rag.ingest import index_pdf, pending_pdfs


def main():
    print("=" * 60)
    print("Pakistan Law AI Assistant — index new law PDFs")
    print("Put files in docs/pdfs then run this script.")
    print("Already indexed documents, including the Constitution, are skipped.")
    print("=" * 60)
    print()

    waiting = pending_pdfs()
    if not waiting:
        print("No new PDFs found in docs/pdfs.")
        return

    for item in waiting:
        print(f"- {item['filename']} -> {item['document_name']}")
    print()

    def report(message, percent=None):
        if percent is None:
            print(message)
        else:
            print(f"[{percent:3d}%] {message}")

    for item in waiting:
        result = index_pdf(
            item["path"],
            document_name=item["document_name"],
            progress=report,
        )
        status = result.get("status")
        document = result.get("document") or {}
        print(
            f"{status}: {document.get('document_name')} "
            f"({document.get('chunk_count', 0)} chunks, "
            f"{result.get('skipped', 0)} skipped, "
            f"{result.get('generated_now', 0)} new embeddings)"
        )
        print()


if __name__ == "__main__":
    main()
