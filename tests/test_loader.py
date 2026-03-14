"""Loader tests for format support and clear PDF failure modes."""

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.loader import load_document


def _write_pdf_with_text(path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1"))
    content_ref = writer._add_object(content)
    page[NameObject("/Contents")] = content_ref

    with path.open("wb") as output_file:
        writer.write(output_file)


def _write_empty_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with path.open("wb") as output_file:
        writer.write(output_file)


def test_load_document_reads_pdf_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _write_pdf_with_text(pdf_path, "Hello PDF Loader")

    document = load_document(str(pdf_path))

    assert document.source.endswith("sample.pdf")
    assert "Hello PDF Loader" in document.text


def test_load_document_raises_on_empty_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "empty.pdf"
    _write_empty_pdf(pdf_path)

    with pytest.raises(ValueError, match="PDF is empty or has no extractable text"):
        load_document(str(pdf_path))


def test_load_document_raises_on_broken_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"this is not a real pdf")

    with pytest.raises(ValueError, match="Failed to parse PDF"):
        load_document(str(pdf_path))
