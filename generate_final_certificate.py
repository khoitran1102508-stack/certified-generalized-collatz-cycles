#!/usr/bin/env python3
"""Public entry point for deterministic certificate generation and verification."""
from pathlib import Path
import runpy

SCRIPT = Path(__file__).resolve().parent / "scripts" / "generate_certificate.py"
runpy.run_path(str(SCRIPT), run_name="__main__")
