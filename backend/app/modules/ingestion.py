from io import BytesIO
from app.modules import repository as repo

def ingest(document_id, owner, content, extension):
    try:
        repo.update(document_id, owner, {"status": "PARSING", "error": None, "chunks": []})
        if extension == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            if len(reader.pages) > 500:
                raise ValueError("PDF limit: 500 pages")
            pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
        else:
            pages = [(1, content.decode("utf-8-sig"))]
        repo.update(document_id, owner, {"status": "CHUNKING"})
        chunks = []
        for page, text in pages:
            words = text.split()
            for start in range(0, len(words), 220):
                chunks.append({"text": " ".join(words[start:start + 260]), "page": page, "chunk_id": f"{document_id}:{page}:{start}"})
        if not chunks:
            raise ValueError("No text found. OCR is not supported.")
        repo.update(document_id, owner, {"status": "READY", "chunks": chunks, "chunk_count": len(chunks)})
    except Exception as exc:
        message = str(exc) if isinstance(exc, (ValueError, UnicodeError)) else "Cannot parse PDF"
        repo.update(document_id, owner, {"status": "FAILED", "error": message})
