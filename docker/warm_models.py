"""Build-time only — not part of the app. Instantiating each model class downloads its
ONNX weights into $FASTEMBED_CACHE_PATH, which the Dockerfile then bakes into the image
layer (docs/aws-architecture.md §3). Model names/languages must stay in sync with
app/ingestion/embed.py and app/retrieval/rerank.py — this intentionally imports their
constants rather than re-declaring them, so a model bump there is picked up here too.
"""

from __future__ import annotations

# Run with CWD=/build (this file's own directory, copied there by the Dockerfile's
# `models` stage) so `app/` resolves as a sibling package — no sys.path hacking needed.
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from fastembed.sparse.bm25 import Bm25

from app.ingestion.embed import DENSE_MODEL, _SPARSE_LANGUAGE, _SPARSE_MODEL
from app.retrieval.rerank import _MODEL as RERANK_MODEL

print(f"Warming dense embedder: {DENSE_MODEL}")
TextEmbedding(model_name=DENSE_MODEL)

print(f"Warming sparse embedder: {_SPARSE_MODEL} ({_SPARSE_LANGUAGE})")
Bm25(model_name=_SPARSE_MODEL, language=_SPARSE_LANGUAGE)

print(f"Warming reranker: {RERANK_MODEL}")
TextCrossEncoder(model_name=RERANK_MODEL)

print("Model warm-up complete.")

# ---------------------------------------------------------------------------
# Docling (app/ingestion/parse.py). Its layout/table models come from the HuggingFace
# hub ($HF_HOME) and RapidOCR's ONNX models land in site-packages/rapidocr/models/; both
# are otherwise downloaded on the first ingest of every fresh worker pod. Rather than
# listing model names (which change across Docling releases), parse a small image-only
# PDF through the real DoclingParser: no text layer -> default converter, then the OCR
# converter, i.e. exactly the models and code path ingestion uses at runtime.
# ---------------------------------------------------------------------------
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

from app.ingestion.parse import DoclingParser  # noqa: E402

print("Warming Docling (layout + table structure + RapidOCR)")
with tempfile.TemporaryDirectory() as tmp:
    pdf_path = Path(tmp) / "warmup.pdf"
    page = Image.new("RGB", (1240, 1754), "white")  # A4 at 150 dpi
    draw = ImageDraw.Draw(page)
    for i, line in enumerate(["BCEAO - Instruction de test", "Article 1. Objet.", "Article 2. Champ."]):
        draw.text((120, 150 + i * 60), line, fill="black")
    page.save(pdf_path, "PDF", resolution=150)
    parsed = DoclingParser()._parse_sync(pdf_path, source_url="warmup", source_location=str(pdf_path))
    print(f"Docling warm-up parsed {len(parsed.pages)} page(s)")

print("Docling warm-up complete.")
