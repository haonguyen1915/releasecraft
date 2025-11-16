from __future__ import annotations

from typing import Any, Type

from ..schemas import ReleaseNotes


class ProviderError(Exception):
    pass


def _import_clients():  # pragma: no cover - import-time side effects
    try:
        import instructor  # type: ignore
        from openai import OpenAI  # type: ignore
        return instructor, OpenAI
    except Exception as e:
        raise ProviderError(
            "OpenAI/Instructor libraries not available. Install 'openai' and 'instructor' packages."
        ) from e


def generate_release_notes(
    *,
    api_key: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
) -> ReleaseNotes:
    """Invoke Instructor+OpenAI to produce structured ReleaseNotes."""
    instructor, OpenAI = _import_clients()
    client = OpenAI(api_key=api_key)
    inst = instructor.from_openai(client)  # type: ignore[attr-defined]

    try:  # pragma: no cover - external call
        rn = inst.chat.completions.create(
            model=model,
            response_model=ReleaseNotes,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:  # surface as provider error
        raise ProviderError(str(e)) from e
    # Instructor returns model instance
    if isinstance(rn, ReleaseNotes):
        return rn
    # Fallback construct
    return ReleaseNotes(**rn)  # type: ignore[arg-type]
