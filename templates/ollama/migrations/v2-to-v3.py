#!/usr/bin/env python3
"""
Migration: ollama v2 → v3.

This is a config/pod-only hop, no on-disk data migration.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("Ollama v2 → v3: config/pod-only hop, no on-disk data migration.")
    print("  - Bumped default OLLAMA_DEFAULT_MODEL to gemma4:12b.")
    print("  - Changed default OLLAMA_EXTRA_MODELS to empty string.")
    print("  Nothing to move or transform on disk; proceeding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
