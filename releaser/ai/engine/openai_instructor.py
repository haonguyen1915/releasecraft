"""OpenAI + Instructor engine helpers.

This module provides a thin wrapper to generate structured chat completions
using the Instructor library on top of the OpenAI Python SDK.

Notes:
- Imports for third‑party clients are done lazily via `_import_clients` so the
  module can be imported even when those packages are not installed. Tests can
  monkeypatch `_import_clients` to inject fakes.
"""

from __future__ import annotations

from typing import Any, Type, TypeVar, Optional
import os
from pathlib import Path

from pydantic import BaseModel

from releaser.ai.schemas import ReleaseNotes


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
            raise TypeError("Could not parse structured response into the response_model") from exc


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
        raise ValueError("API key is required for AI release notes generation")

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
    user_prompt = _render_template(
        user_template,
        commits=commits,
        current_version=current_version,
        previous_version=previous_version,
        diffs=diffs or {},
    )

    # Generate structured output using the generic function
    return generate_structured(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_template,
        user_prompt=user_prompt,
        response_model=ReleaseNotes,
    )