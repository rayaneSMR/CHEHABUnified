#!/usr/bin/env python3
"""Run Experiment 2 model evaluations and store the raw CSV results."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from run_model_evaluations import main


if __name__ == "__main__":
    raise SystemExit(main(["--sets", "original", *sys.argv[1:]]))
