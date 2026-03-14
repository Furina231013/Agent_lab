"""Remove generated files so repeated demos start cleanly."""

from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.config import settings


def _clear_generated_files(directory: Path) -> int:
    deleted = 0
    for path in directory.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_file():
            path.unlink()
            deleted += 1
    return deleted


def main() -> None:
    processed_deleted = _clear_generated_files(settings.processed_dir)
    index_deleted = _clear_generated_files(settings.index_dir)
    print(f"deleted_processed={processed_deleted}")
    print(f"deleted_index={index_deleted}")


if __name__ == "__main__":
    main()
