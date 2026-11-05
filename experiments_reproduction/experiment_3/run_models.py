#!/usr/bin/env python3
"""Run Experiment 3 model evaluations and store raw original/threshold CSVs."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from run_model_evaluations import main


if __name__ == "__main__":
    raise SystemExit(main(["--sets", "original,threshold", *sys.argv[1:]]))
