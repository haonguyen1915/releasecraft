from __future__ import annotations

import argparse
import os
import subprocess
from typing import Dict, List, Optional

from .console import logger, prompt_confirmation, bordered
from .config.load import load_config
from .ai.engine.openai_instructor import generate_commit_message


def _run_git(args: List[str]) -> str:
    try:
        res = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
        return res.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git {' '.join(args)} failed: {e}") from e


def _get_staged_files() -> List[str]:
    out = _run_git(["diff", "--staged", "--name-only"])
    files = [line.strip() for line in out.splitlines() if line.strip()]
    return files


def _get_diffs_for_files(files: List[str]) -> Dict[str, str]:
    diffs: Dict[str, str] = {}
    for f in files:
        try:
            text = _run_git(["diff", "--staged", "--", f])
        except RuntimeError:
            text = ""
        diffs[f] = text
    return diffs


def _get_recent_commit_subjects(n: int) -> List[str]:
    if n <= 0:
        return []
    try:
        out = _run_git(["log", f"-n{n}", "--pretty=%s"])
        subjects = [line.strip() for line in out.splitlines() if line.strip()]
        # Filter out merge commits for signal clarity
        subjects = [s for s in subjects if not s.lower().startswith("merge ")]
        return subjects
    except Exception:
        return []


def run(args: argparse.Namespace) -> int:
    # Resolve file list
    files: List[str] = []
    if getattr(args, "staged", False):
        files.extend(_get_staged_files())
    files_arg = getattr(args, "files", []) or []
    files.extend(files_arg)
    # Deduplicate while preserving order
    seen = set()
    files = [f for f in files if not (f in seen or seen.add(f))]

    if not files:
        logger.error(
            "No files provided and no staged changes. Use --staged or --files."
        )
        return 1

    # Build diffs mapping per file
    diffs = _get_diffs_for_files(files)

    # Load AI/config defaults
    cfg = load_config(getattr(args, "config", None))
    ai_cfg = getattr(cfg, "ai", None)
    api_key = (
        None
        if getattr(args, "no_ai", False)
        else os.environ.get(getattr(ai_cfg, "api_key_env", "OPENAI_API_KEY"))
    )
    model = getattr(args, "model", None) or getattr(ai_cfg, "model", "gpt-4o-mini")
    try:
        temperature = float(
            getattr(args, "temperature", None) or getattr(ai_cfg, "temperature", 0.2)
        )
    except Exception:
        temperature = 0.2
    try:
        max_tokens = int(
            getattr(args, "max_tokens", None) or getattr(ai_cfg, "max_tokens", 600)
        )
    except Exception:
        max_tokens = 600

    # Determine history count (CLI overrides config when provided)
    history_opt = getattr(args, "history", None)
    if history_opt is None:
        history_n = int(
            getattr(getattr(cfg, "commit_gen", None), "history_commits", 10)
        )
    else:
        history_n = int(history_opt)

    # Generate commit message (AI or heuristic)
    recent_subjects: List[str] = _get_recent_commit_subjects(history_n)
    cm = generate_commit_message(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        files=files,
        diffs=diffs,
        ticket=getattr(args, "ticket", None),
        system_prompt_file=getattr(args, "system_prompt_file", None),
        user_prompt_file=getattr(args, "user_prompt_file", None),
        recent_subjects=recent_subjects,
        demote_feat_if_similar=bool(
            getattr(getattr(cfg, "commit_gen", None), "demote_feat_if_similar", True)
        ),
    )

    text = cm.to_text()

    # Output destination
    out_path: Optional[str] = getattr(args, "output", None)
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            logger.success(f"Wrote commit message to {out_path}")
        except Exception as e:
            logger.error(f"Failed to write commit message to {out_path}: {e}")
            return 1
    else:
        # Display the generated commit message
        bordered.create_bordered_content(
            text, title="Generated Commit Message", dry_run=False
        )

        # Check if --yes flag is set
        auto_commit = getattr(args, "yes", False)

        # Ask user if they want to commit (or auto-commit if --yes)
        should_commit = auto_commit or prompt_confirmation(
            "Do you want to create a commit with this message?", default=True
        )

        if should_commit:
            try:
                # Create the commit
                subprocess.run(
                    ["git", "commit", "-m", text],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.success("Commit created successfully!")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to create commit: {e.stderr}")
                return 1
        else:
            logger.info("Commit not created. You can copy the message above if needed.")

    return 0
