"""Neutral local-storage defaults shared by canonical data-source adapters."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESEARCH_DIR = PROJECT_ROOT / "data" / "processed" / "dividend_t"
