"""Tests for document generation and the /documento request parser."""

import pytest

from ev.interfaces.telegram_bot import TelegramInterface
from ev.providers import documents


def test_normalize_format_aliases():
    assert documents.normalize_format("word") == "docx"
    assert documents.normalize_format("PDF") == "pdf"
    assert documents.normalize_format("texto") == "txt"
    assert documents.normalize_format("xyz") is None


def test_slugify():
    assert documents.slugify("Lista de Compras!") == "lista_de_compras"
    assert documents.slugify("") == "documento"


@pytest.mark.parametrize("fmt,ext", [("txt", "txt"), ("md", "md"), ("pdf", "pdf"), ("word", "docx")])
def test_build_each_format(fmt, ext):
    data, filename = documents.build(fmt, "Meu Título", "Olá, mundo.\nSegunda linha com acento: ção.")
    assert filename.endswith(f".{ext}")
    assert isinstance(data, bytes) and len(data) > 0


def test_build_pdf_signature():
    data, _ = documents.build("pdf", "T", "conteúdo")
    assert data[:4] == b"%PDF"  # valid PDF header


def test_build_docx_is_zip():
    data, _ = documents.build("docx", "T", "conteúdo")
    assert data[:2] == b"PK"  # docx is a zip container


def test_build_rejects_unknown_format():
    with pytest.raises(ValueError):
        documents.build("xls", "T", "c")


def test_parse_doc_request_with_format():
    fmt, title, content, err = TelegramInterface._parse_doc_request("pdf Lista | arroz, feijão")
    assert err is None
    assert fmt == "pdf" and title == "Lista" and content == "arroz, feijão"


def test_parse_doc_request_defaults_to_pdf():
    fmt, title, content, err = TelegramInterface._parse_doc_request("Minhas notas | texto aqui")
    assert err is None
    assert fmt == "pdf" and title == "Minhas notas" and content == "texto aqui"


def test_parse_doc_request_requires_content():
    _, _, _, err = TelegramInterface._parse_doc_request("pdf só título")
    assert err is not None
