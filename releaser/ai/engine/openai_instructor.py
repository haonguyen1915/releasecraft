"""OpenAI + Instructor engine helpers.

This module provides a thin wrapper to generate structured chat completions
using the Instructor library on top of the OpenAI Python SDK.

Notes:
- Imports for third‑party clients are done lazily via `_import_clients` so the
  module can be imported even when those packages are not installed. Tests can
  monkeypatch `_import_clients` to inject fakes.
"""

from __future__ import annotations

from typing import Any, Type, TypeVar, Optional, Iterable
import difflib
from pathlib import Path

from pydantic import BaseModel

from releaser.ai.schemas import ReleaseNotes, CommitMessage


def _import_clients() -> tuple[Any, Any]:
    """Import and return (instructor_module, OpenAI_class).

    Done lazily so the module can be imported without optional deps; tests can
    monkeypatch this function.
    """
    try:  # pragma: no cover - exercised in real usage
        import instructor as _instructor
    except Exception as exc:  # pragma: no cover - exercised in real usage
        raise ImportError(
            "Instructor package is required for AI features. Install 'instructor'."
        ) from exc

    try:  # pragma: no cover - exercised in real usage
        from openai import OpenAI as _OpenAI
    except Exception as exc:  # pragma: no cover - exercised in real usage
        raise ImportError(
            "OpenAI package is required for AI features. Install 'openai'."
        ) from exc

    return _instructor, _OpenAI


T = TypeVar("T", bound=BaseModel)


class _RNFallback(ReleaseNotes):
    # Ensure attributes exist for consumers that access them
    sections: list = []
    limitations: list = []


def generate_structured(
    *,
    api_key: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
) -> T:
    """Generate a structured response parsed into a Pydantic model.

    This is a generic helper over the Instructor+OpenAI integration that can
    produce any `BaseModel` subclass, not just release notes.
    """

    instructor_mod, OpenAICls = _import_clients()

    # Instantiate raw OpenAI client and patch it via Instructor
    oa_client = OpenAICls(api_key=api_key)
    client = instructor_mod.from_openai(oa_client)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result: Any = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=messages,
        response_model=response_model,
    )

    # In normal operation, `result` is already an instance of `response_model`.
    if isinstance(result, response_model):  # type: ignore[arg-type]
        return result

    # Fallback: attempt to construct model from mapping-like response.
    if isinstance(result, dict):  # pragma: no cover - defensive
        try:
            return response_model(**result)
        except Exception:
            pass

    # Generic resilience: try common field 'summary' if present; otherwise try default ctor.
    try:  # pragma: no cover - defensive
        return response_model(**{"summary": str(result)})
    except Exception:
        try:
            return response_model()  # type: ignore[call-arg]
        except Exception as exc:
            raise TypeError(
                "Could not parse structured response into the response_model"
            ) from exc


DEFAULT_SYSTEM_PROMPT_RELEASE_NOTES = (
    "You are an assistant that prepares clear, user-focused release notes. "
    "Summarize changes for end users and developers without leaking internal details. "
    "Identify breaking changes (type! or BREAKING CHANGE), major features, bug fixes, and notable improvements. "
    "Use concise, action-oriented phrasing."
)


def _import_jinja2() -> Any:
    """Import and return jinja2 module.

    Done lazily so the module can be imported without optional deps; tests can
    monkeypatch this function.
    """
    try:  # pragma: no cover - exercised in real usage
        import jinja2 as _jinja2
    except Exception as exc:  # pragma: no cover - exercised in real usage
        raise ImportError(
            "Jinja2 package is required for template rendering. Install 'jinja2'."
        ) from exc
    return _jinja2


def _load_template(
    custom_path: str | None,
    default_filename: str,
) -> str:
    """Load a template file from custom path or default location.

    Args:
        custom_path: User-provided custom template path (from config)
        default_filename: Filename in releaser/ai/prompts/ to use as fallback

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If custom path specified but not found
    """
    # If custom path provided, use it
    if custom_path:
        custom_file = Path(custom_path)
        if not custom_file.exists():
            raise FileNotFoundError(f"Custom template not found: {custom_path}")
        return custom_file.read_text(encoding="utf-8")

    # Otherwise, use default from prompts directory
    prompts_dir = Path(__file__).parent.parent / "prompts"
    default_file = prompts_dir / default_filename

    if not default_file.exists():
        raise FileNotFoundError(
            f"Default template not found: {default_file}. "
            f"Expected at {prompts_dir}/{default_filename}"
        )

    return default_file.read_text(encoding="utf-8")


def _render_template(template_str: str, **context: Any) -> str:
    """Render a Jinja2 template string with given context.

    Args:
        template_str: Jinja2 template content
        **context: Template variables

    Returns:
        Rendered template string
    """
    jinja2 = _import_jinja2()
    template = jinja2.Template(template_str)
    return template.render(**context)


def _infer_cc_from_heuristics(
    *, files: list[str], diffs: dict[str, str] | None = None, allow_scope: bool = True
) -> CommitMessage:
    """Heuristic commit message generator when AI is unavailable.

    - Determines type by file patterns and diff content
    - Infers scope from primary top-level directory
    - Produces a short subject
    """
    diffs = diffs or {}
    lowered = [f.lower() for f in files]

    # Type heuristics
    def only(exts=None, prefixes=None):
        exts = exts or []
        prefixes = prefixes or []
        return all(
            (any(f.endswith(e) for e in exts) if exts else True)
            and (any(f.startswith(p) for p in prefixes) if prefixes else True)
            for f in lowered
        )

    if (
        files
        and only(exts=[".md", ".rst"])
        or all(f.startswith("docs/") for f in lowered)
    ):
        ctype = "docs"
        subject = "update documentation"
    elif files and all(f.startswith("tests/") for f in lowered):
        ctype = "test"
        subject = "update tests"
    elif any(
        p in files
        for p in [
            "pyproject.toml",
            "setup.cfg",
            "package.json",
            ".pre-commit-config.yaml",
        ]
    ):
        ctype = "build"
        subject = "update build configuration"
    elif any(f.startswith(".github/") or f.startswith(".gitlab") for f in lowered):
        ctype = "ci"
        subject = "update CI configuration"
    else:
        # Analyze diff content for common signals
        added = "\n".join([d for d in diffs.values()])
        added_lower = added.lower()
        if "fix" in added_lower or "bug" in added_lower or "error" in added_lower:
            ctype = "fix"
            subject = "fix issues"
        elif "+def " in added or "+class " in added:
            ctype = "feat"
            subject = "add functionality"
        elif "refactor" in added_lower:
            ctype = "refactor"
            subject = "refactor code"
        else:
            ctype = "chore"
            subject = "update files"

    # Scope: choose first non-root top-level dir
    scope = None
    if allow_scope:
        for f in files:
            parts = f.split("/")
            if len(parts) > 1 and parts[0] not in {"tests", "docs"}:
                scope = parts[0]
                break

    return CommitMessage(type=ctype, scope=scope, subject=subject)


def _normalize_subject(s: str) -> str:
    return "".join(ch for ch in s.lower().strip() if ch.isalnum() or ch.isspace())


def _maybe_demote_feat(
    cm: CommitMessage, diffs: dict[str, str], recent_subjects: Optional[Iterable[str]]
) -> CommitMessage:
    if cm.type != "feat" or not cm.subject:
        return cm
    subjects = list(recent_subjects or [])
    if not subjects:
        return cm
    norm = _normalize_subject(cm.subject)
    for s in subjects:
        if not s:
            continue
        if difflib.SequenceMatcher(None, norm, _normalize_subject(s)).ratio() >= 0.85:
            # Check added lines count: if relatively low, consider it an iteration
            added = 0
            for d in (diffs or {}).values():
                for line in d.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        added += 1
            if added < 40:  # heuristic threshold
                cm.type = "refactor"
            return cm
    return cm


def generate_commit_message(
    *,
    api_key: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    files: list[str],
    diffs: dict[str, str],
    ticket: str | None = None,
    allow_scope: bool = False,
    system_prompt_file: str | None = None,
    user_prompt_file: str | None = None,
    recent_subjects: Optional[list[str]] = None,
    demote_feat_if_similar: bool = True,
) -> CommitMessage:
    """Generate a Conventional Commit message from diffs and file list.

    When AI dependencies or API key are unavailable, falls back to heuristics.
    """
    # AI unavailable: heuristics
    if not api_key:
        cm = _infer_cc_from_heuristics(
            files=files, diffs=diffs, allow_scope=allow_scope
        )
        if demote_feat_if_similar:
            cm = _maybe_demote_feat(cm, diffs, recent_subjects)
        if ticket:
            cm.footers = {"Refs": ticket}
        return cm

    # Load templates
    system_template = _load_template(
        custom_path=system_prompt_file,
        default_filename="system_commit_message.md",
    )
    user_template = _load_template(
        custom_path=user_prompt_file,
        default_filename="commit_message.md.j2",
    )

    # Render user prompt
    try:
        user_prompt = _render_template(
            user_template,
            files=files,
            diffs=diffs,
            ticket=ticket or "",
            allow_scope=allow_scope,
            recent_subjects=recent_subjects or [],
        )
    except ImportError:
        # Fallback without Jinja2
        diff_preview = "\n\n".join(
            f"--- {p} ---\n{d[:2000]}" for p, d in list(diffs.items())[:5]
        )
        files_preview = "\n".join(f"- {f}" for f in files)
        user_prompt = (
            f"Files changed:\n{files_preview}\n\nDiff excerpts:\n{diff_preview}\n\n"
            "Write a Conventional Commit message with type, optional scope, subject and body."
        )

    # AI path
    try:
        cm = generate_structured(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_template,
            user_prompt=user_prompt,
            response_model=CommitMessage,
        )
        if not allow_scope:
            cm.scope = None
        if demote_feat_if_similar:
            cm = _maybe_demote_feat(cm, diffs, recent_subjects)
        return cm
    except ImportError:
        # As a last resort
        cm = _infer_cc_from_heuristics(
            files=files, diffs=diffs, allow_scope=allow_scope
        )
        if demote_feat_if_similar:
            cm = _maybe_demote_feat(cm, diffs, recent_subjects)
        if ticket:
            cm.footers = {"Refs": ticket}
        return cm


def generate_release_notes(
    *,
    api_key: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    commits: list[dict[str, Any]],
    current_version: str,
    previous_version: str,
    diffs: dict[str, str] | None = None,
    include_diff: Optional[bool] = None,
    max_commits: Optional[int] = None,
    always_diff_types: Optional[list[str]] = None,
    system_prompt_file: str | None = None,
    user_prompt_file: str | None = None,
) -> ReleaseNotes:
    """Generate release notes using AI based on commits and code changes.

    This function analyzes version control history to produce structured release notes
    using the OpenAI + Instructor integration.

    Args:
        api_key: OpenAI API key (required)
        model: Model name (e.g., "gpt-4o-mini")
        temperature: Sampling temperature (0.0-2.0, lower = more deterministic)
        max_tokens: Maximum tokens for response
        commits: List of commit dictionaries with keys:
            - hash: Commit SHA
            - message: Commit message
            - author: Author name/email
            - date: Commit date
        current_version: New version being released
        previous_version: Previous version tag
        diffs: Optional dict mapping commit hash to diff text (for important commits)
        system_prompt_file: Optional custom system prompt file path
        user_prompt_file: Optional custom user prompt template file path

    Returns:
        ReleaseNotes: Structured release notes with summary, highlights, sections, etc.

    Raises:
        ImportError: If jinja2, instructor, or openai packages are not installed
        FileNotFoundError: If custom template paths are invalid
        ValueError: If API key is missing or invalid
        TypeError: If response cannot be parsed into ReleaseNotes model

    Example:
        >>> commits = [
        ...     {
        ...         "hash": "abc123def456",
        ...         "message": "feat: add dark mode support",
        ...         "author": "Jane Doe <jane@example.com>",
        ...         "date": "2024-01-15"
        ...     },
        ...     {
        ...         "hash": "def456abc123",
        ...         "message": "fix: resolve memory leak in cache",
        ...         "author": "John Smith <john@example.com>",
        ...         "date": "2024-01-14"
        ...     }
        ... ]
        >>> notes = generate_release_notes(
        ...     api_key="sk-...",
        ...     model="gpt-4o-mini",
        ...     temperature=0.2,
        ...     max_tokens=800,
        ...     commits=commits,
        ...     current_version="1.2.0",
        ...     previous_version="1.1.0"
        ... )
        >>> print(notes.to_markdown())
    """
    if not api_key:
        # If no commits provided, cannot draft meaningful notes without AI
        if not commits:
            raise ValueError("API key is required for AI release notes generation")
        # Fallback: construct minimal release notes without calling AI
        highlights = [c.get("message", "") for c in commits[:5] if c.get("message")]
        summary = (
            f"Release notes draft for {current_version} (prev: {previous_version})"
        )
        rn = _RNFallback(
            summary=summary,
            highlights=highlights,
            sections=[],
            breaking_changes=[],
            limitations=[],
        )
        return rn

    # Determine effective options (include_diff, max_commits, always_diff_types)
    if include_diff is None or max_commits is None or always_diff_types is None:
        try:
            from releaser.config.load import load_config  # type: ignore
            from releaser.ai.config import AiConfig  # type: ignore

            _cfg = load_config()
            _ai = AiConfig.from_app_config(_cfg)
        except Exception:
            _ai = None  # type: ignore
        if include_diff is None:
            include_diff = bool(getattr(_ai, "include_diff", True)) if diffs else False
        if max_commits is None:
            max_commits = int(getattr(_ai, "max_commits", 0)) or None
        if always_diff_types is None:
            always_diff_types = list(getattr(_ai, "always_diff_types", []) or [])

    # Limit commits per max_commits (most recent first as provided)
    commits_limited = commits[:max_commits] if max_commits else commits

    # Filter diffs by include_diff and always_diff_types
    def _ctype(msg: str) -> str:
        # Parse conventional commit type from message header
        head = (msg or "").split(":", 1)[0]
        head = head.split("(", 1)[0]
        return head.strip().lower()

    selected_diffs: dict[str, str] = {}
    if diffs and (include_diff or always_diff_types):
        if include_diff:
            selected_diffs = dict(diffs)
        else:
            # Include diffs only for commits matching types in always_diff_types
            type_set = {t.strip().lower() for t in (always_diff_types or []) if t}
            if type_set:
                for c in commits_limited:
                    try:
                        ctype = _ctype(str(c.get("message", "")))
                        chash = str(c.get("hash", ""))
                        if ctype in type_set and chash in (diffs or {}):
                            selected_diffs[chash] = diffs[chash]
                    except Exception:
                        continue

    # Load templates
    system_template = _load_template(
        custom_path=system_prompt_file,
        default_filename="system_release_notes.md",
    )

    user_template = _load_template(
        custom_path=user_prompt_file,
        default_filename="release_notes.md.j2",
    )

    # Render user prompt with Jinja2 using provided context
    try:
        user_prompt = _render_template(
            user_template,
            commits=commits_limited,
            current_version=current_version,
            previous_version=previous_version,
            diffs=selected_diffs,
        )
    except ImportError:
        # Fallback rendering without Jinja2
        commit_lines = "\n".join(
            f"- {c.get('message','')} ({c.get('hash','')[:7]})" for c in commits_limited
        )
        user_prompt = (
            f"Target version: {current_version}\nPrevious version: {previous_version}\n\n"
            f"Commits since last release:\n{commit_lines}\n\n"
            "Please produce structured release notes with summary, highlights, breaking changes, and grouped sections."
        )

    # Generate structured output using the generic function
    try:
        return generate_structured(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_template,
            user_prompt=user_prompt,
            response_model=ReleaseNotes,
        )
    except ImportError:
        # If AI libs are not available, return a non-AI draft for graceful degradation
        highlights = [c.get("message", "") for c in commits[:5] if c.get("message")]
        summary = (
            f"Release notes draft for {current_version} (prev: {previous_version})"
        )
        rn = _RNFallback(
            summary=summary,
            highlights=highlights,
            sections=[],
            breaking_changes=[],
            limitations=[],
        )
        return rn
