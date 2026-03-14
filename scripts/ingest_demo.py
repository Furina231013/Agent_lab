"""Run the ingest pipeline without the web server.

This mirrors the service flow used by the API and is useful when you want to
learn the backend pieces one step at a time.
"""

from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.config import to_relative_path
from app.services.chunker import chunk_text
from app.services.loader import load_document
from app.services.storage import save_chunks


def main() -> None:
    document = load_document("data/raw/demo.md")
    chunks = chunk_text(source=document.source, text=document.text)
    output_path = save_chunks(source=document.source, chunks=chunks)
    print(f"source={document.source}")
    print(f"chunk_count={len(chunks)}")
    print(f"output_path={to_relative_path(output_path)}")


if __name__ == "__main__":
    main()
