from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def read_notes_from_editor(initial_text: str = "") -> str:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        "w+", delete=False, suffix=".tmp", prefix="releaser_notes_"
    ) as tf:
        path = tf.name
        if initial_text:
            tf.write(initial_text)
        tf.flush()
    try:
        subprocess.run([editor, path], check=False)
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def normalize_notes(notes: Optional[str]) -> str:
    return (notes or "").strip()


def append_changelog(
    changelog_path: str, tag_name: str, date_str: str, notes: str
) -> None:
    """Deprecated compatibility wrapper.

    Historically accepted notes-only and built the header internally.
    Prefer using `append_changelog_block` with a fully rendered block.
    """
    header = f"## {tag_name} – {date_str}\n\n"
    block = header
    if notes:
        block += notes.strip() + "\n\n"
    append_changelog_block(changelog_path, block)


def append_changelog_block(changelog_path: str, block: str) -> None:
    """Prepend a fully-rendered changelog block to the file.

    Creates the file with a top-level title if it does not exist.
    """
    p = Path(changelog_path)
    title = "# Changelog\n\n"
    if p.exists():
        existing = p.read_text(encoding="utf-8")
        p.write_text(block + existing)
    else:
        p.write_text(title + block, encoding="utf-8")
