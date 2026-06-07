#!/usr/bin/env python3
"""
Migration: ollama v1 → v2.

This is a config/pod-only hop, no on-disk data migration.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("Ollama v1 → v2: config/pod-only hop, no on-disk data migration.")
    print("  - Added OLLAMA_EXTRA_MODELS variable.")
    print("  - Bumped default OLLAMA_DEFAULT_MODEL to gemma4:e4b.")
    print("  - Updated pull_model verification.")
    print("  Nothing to move or transform on disk; proceeding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
