"""Parser settings shared by the PDF parser and the run metadata (W2, D-024)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCLING_MODELS = ROOT / "var/models/docling"
PDF_OPTIONS = {"do_ocr": False, "do_table_structure": True}
