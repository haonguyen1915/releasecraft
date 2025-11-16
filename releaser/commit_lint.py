from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .console import logger
from .config.load import load_config


@dataclass
class Violation:
    rule: str
    message: str


HEADER_RE_TEMPLATE = (
    r"^(?P<type>{types})(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: (?P<subject>.+)$"
)


def _read_commit_message(path: Optional[str]) -> str:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip("\n")
    # Fallback to standard location
    default_path = os.path.join(".git", "COMMIT_EDITMSG")
    if os.path.exists(default_path):
        with open(default_path, "r", encoding="utf-8") as f:
            return f.read().strip("\n")
    return ""


def _split_message(msg: str) -> Tuple[str, str]:
    lines = msg.splitlines()
    header = lines[0] if lines else ""
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return header, body


def _compile_header_regex(types: List[str]) -> re.Pattern[str]:
    safe_types = [re.escape(t) for t in types]
    pattern = HEADER_RE_TEMPLATE.format(types="|".join(safe_types))
    return re.compile(pattern)


def _validate_scope(
    scope: Optional[str], require: bool, allowed: List[str], pattern: Optional[str]
) -> Optional[Violation]:
    if require and not scope:
        return Violation("scope.required", "Scope is required: type(scope): subject")
    if not scope:
        return None
    if allowed and scope not in allowed:
        return Violation(
            "scope.allowed", f"Scope '{scope}' not in allowed list: {allowed}"
        )
    if pattern:
        if not re.fullmatch(pattern, scope or ""):
            return Violation(
                "scope.pattern", f"Scope '{scope}' does not match pattern: {pattern}"
            )
    return None


def _find_ticket(msg: str, ticket_pattern: Optional[str]) -> bool:
    if not ticket_pattern:
        return True
    return re.search(ticket_pattern, msg) is not None


def validate_commit_message(msg: str) -> List[Violation]:
    cfg = load_config()
    c = cfg.commit_lint

    header, body = _split_message(msg.strip())

    # Skip merge/revert commits when configured
    if c.skip_merge_commits and header.startswith("Merge "):
        return []
    if c.skip_revert_commits and header.startswith("Revert "):
        return []

    violations: List[Violation] = []

    header_re = _compile_header_regex(c.types)
    m = header_re.match(header)
    if not m:
        violations.append(
            Violation(
                "header.format",
                "Invalid header. Expected: type[(scope)][!]: subject (e.g., 'feat(core): add X')",
            )
        )
        return violations

    _typ = m.group("type")
    scope = m.group("scope")
    bang = bool(m.group("bang"))
    subject = m.group("subject") or ""

    # Bang handling
    if bang and not c.allow_bang:
        violations.append(
            Violation("bang.disallowed", "'!' breaking indicator is not allowed")
        )

    # Scope rules
    v = _validate_scope(scope, c.require_scope, c.scopes, c.scope_pattern)
    if v:
        violations.append(v)

    # Subject rules
    if not subject or subject.strip() == "":
        violations.append(
            Violation("subject.required", "Subject must not be empty after colon")
        )
    if len(subject) > max(1, int(c.subject_max_length)):
        violations.append(
            Violation(
                "subject.length",
                f"Subject too long ({len(subject)} > {c.subject_max_length})",
            )
        )

    # Ticket requirement
    if c.require_ticket and not _find_ticket(msg, c.ticket_pattern):
        violations.append(Violation("ticket.required", "Ticket reference not found"))

    # Breaking change footer: allowed when present; we don't enforce its presence
    if not c.allow_breaking_footer and (
        "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body
    ):
        violations.append(
            Violation(
                "breaking_footer.disallowed", "'BREAKING CHANGE' footer is not allowed"
            )
        )

    return violations


def run(args: argparse.Namespace) -> int:
    """Entry point for CLI command."""
    # Commit message file may be passed as the last positional argument by pre-commit
    path = None
    if getattr(args, "files", None):
        # pre-commit may pass multiple files but commit-msg stage passes one
        path = args.files[0]
    elif getattr(args, "file", None):
        path = args.file

    msg = _read_commit_message(path)
    if not msg:
        logger.error("No commit message found to lint")
        return 2

    violations = validate_commit_message(msg)
    if not violations:
        if getattr(args, "format", "text") == "text":
            logger.success("Commit message passes Conventional Commit rules")
        else:
            print(json.dumps({"ok": True, "violations": []}))
        return 0

    # Output
    if getattr(args, "format", "text") == "json":
        print(
            json.dumps(
                {
                    "ok": False,
                    "violations": [v.__dict__ for v in violations],
                }
            )
        )
    else:
        logger.error("Conventional Commit violations:")
        for v in violations:
            logger.error(f"- [{v.rule}] {v.message}")
        logger.info(
            "Expected format: type[(scope)][!]: subject — e.g., 'feat(api): add search endpoint'"
        )
    return 1
