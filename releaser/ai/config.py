from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AiConfig:
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.2
    max_tokens: int = 800
    prompt_release_notes_file: str | None = None
    system_prompt_file: str | None = None
    include_diff: bool = False
    max_commits: int = 200
    always_diff_types: list[str] = field(default_factory=list)
    cache: bool = True
    accept_automatically: bool = False
    fail_on_error: bool = False

    @staticmethod
    def from_app_config(cfg) -> "AiConfig":
        ai = getattr(cfg, "ai", None)
        if ai is None:
            return AiConfig()
        return AiConfig(
            enabled=getattr(ai, "enabled", False),
            provider=getattr(ai, "provider", "openai"),
            model=getattr(ai, "model", "gpt-4o-mini"),
            api_key_env=getattr(ai, "api_key_env", "OPENAI_API_KEY"),
            temperature=getattr(ai, "temperature", 0.2),
            max_tokens=getattr(ai, "max_tokens", 800),
            prompt_release_notes_file=getattr(ai, "prompt_release_notes_file", None),
            system_prompt_file=getattr(ai, "system_prompt_file", None),
            include_diff=getattr(ai, "include_diff", False),
            max_commits=getattr(ai, "max_commits", 200),
            always_diff_types=list(getattr(ai, "always_diff_types", []) or []),
            cache=getattr(ai, "cache", True),
            accept_automatically=getattr(ai, "accept_automatically", False),
            fail_on_error=getattr(ai, "fail_on_error", False),
        )
