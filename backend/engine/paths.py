"""Where the kit data lives. KIT_ROOT overrides it; the default is the repo root (the parent of backend/)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def kit_root() -> Path:
    """Folder holding master_data/, contracts/, pr_batches/ and the kit PDFs."""
    override = os.environ.get("KIT_ROOT", "").strip()
    return Path(override).resolve() if override else BACKEND_DIR.parent
