"""Backwards-compatible entrypoint. The real generator lives in generate.py.

Run either of:
    python -m backend.data.generate --records 100000 --seed 42
    python3 backend/data/generate_dataset.py            # uses env / defaults
"""
import os
import sys

if __package__ in (None, ""):
    # Executed as a bare script: make the repo root importable.
    _REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from backend.data.generate import main
else:
    from .generate import main

if __name__ == "__main__":
    main()
