"""Single entry point: pick the parser by file type and report failures (W2)."""

import hashlib
import importlib
import zipfile
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

from spec_bridge.parse.blocks import Block, FileFormat, ParsedDocument, ParseError

Parser = Callable[[Path, str], list[Block]]

SUFFIXES: dict[str, FileFormat] = {".pdf": "pdf", ".xlsx": "xlsx", ".docx": "docx", ".md": "md"}
MD_PARSER = "spec-bridge md_parser 1"  # W6-2: our own reader (evaluation inputs only)
LIBRARIES: dict[FileFormat, str] = {
    "pdf": "docling",
    "xlsx": "openpyxl",
    "docx": "python-docx",
}


def detect_format(path: Path, document_id: str) -> FileFormat:
    file_format = SUFFIXES.get(path.suffix.lower())
    if file_format is None:
        raise ParseError(document_id, f"unsupported file type {path.suffix!r}")
    if file_format == "md":
        try:
            path.read_text(encoding="utf-8")
            valid = True
        except UnicodeDecodeError:
            valid = False
    elif file_format == "pdf":
        valid = path.read_bytes()[:5] == b"%PDF-"
    else:
        valid = zipfile.is_zipfile(path)  # xlsx/docx are zip containers
    if not valid:
        raise ParseError(document_id, f"not a valid {file_format} file")
    return file_format


def parse_document(path: Path, document_id: str) -> ParsedDocument:
    """Parse one document; every expected failure becomes ParseError (CP-S2 R1)."""
    try:
        if not path.is_file():
            raise ParseError(document_id, f"cannot read file: {path} does not exist")
        file_format = detect_format(path, document_id)
        module = importlib.import_module(f"spec_bridge.parse.{file_format}_parser")
        parse: Parser = module.parse
        blocks = parse(path, document_id)
        if not blocks:
            raise ParseError(document_id, "no text blocks found")
        library = LIBRARIES.get(file_format)
        parser_name = f"{library} {version(library)}" if library else MD_PARSER
        return ParsedDocument(
            document_id=document_id,
            file_format=file_format,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            parser=parser_name,
            blocks=blocks,
        )
    except ParseError:
        raise
    except OSError as exc:
        raise ParseError(document_id, f"cannot read file: {exc}") from exc
    except Exception as exc:  # library failures become reports, not crashes
        raise ParseError(document_id, f"{type(exc).__name__}: {exc}") from exc
