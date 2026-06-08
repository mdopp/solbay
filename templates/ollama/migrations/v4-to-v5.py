#!/usr/bin/env python3
"""
Migration: ollama v4 → v5.

This is a config/pod-only hop, no on-disk data migration.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("Ollama v4 → v5: config/pod-only hop, no on-disk data migration.")
    print("  - OLLAMA_KEEP_ALIVE default raised from 60m to 24h (#268).")
    print("  - Added OLLAMA_MAX_LOADED_MODELS (default 1).")
    print("  Nothing to move or transform on disk; proceeding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
