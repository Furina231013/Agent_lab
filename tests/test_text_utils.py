"""Text normalization tests for mixed Chinese/PDF output quirks."""

from app.utils.text import normalize_text


def test_normalize_text_removes_artificial_spaces_between_cjk_chars() -> None:
    assert normalize_text("错误 码") == "错误码"
    assert normalize_text("骨 架") == "骨架"


def test_normalize_text_keeps_readable_spaces_for_latin_words() -> None:
    assert normalize_text("FastAPI   service   layer") == "FastAPI service layer"
