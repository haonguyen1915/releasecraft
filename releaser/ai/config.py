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
        """Build AiConfig from AppConfig by combining LLM and auto_gen_notes settings.

        LLM settings come from cfg.llm:
        - provider, model, api_key_env, temperature, max_tokens, cache
        - accept_automatically, fail_on_error
        - prompt_release_notes_file, system_prompt_file

        Auto-gen notes settings come from cfg.release.auto_gen_notes:
        - enabled, include_diff, always_diff_types, max_commits
        """
        llm = getattr(cfg, "llm", None)
        auto_gen = getattr(getattr(cfg, "release", None), "auto_gen_notes", None)

        if llm is None and auto_gen is None:
            return AiConfig()

        return AiConfig(
            # From release.auto_gen_notes
            enabled=getattr(auto_gen, "enabled", False) if auto_gen else False,
            include_diff=getattr(auto_gen, "include_diff", False)
            if auto_gen
            else False,
            always_diff_types=list(getattr(auto_gen, "always_diff_types", []) or [])
            if auto_gen
            else [],
            max_commits=getattr(auto_gen, "max_commits", 200) if auto_gen else 200,
            # From llm
            provider=getattr(llm, "provider", "openai") if llm else "openai",
            model=getattr(llm, "model", "gpt-4o-mini") if llm else "gpt-4o-mini",
            api_key_env=getattr(llm, "api_key_env", "OPENAI_API_KEY")
            if llm
            else "OPENAI_API_KEY",
            temperature=getattr(llm, "temperature", 0.2) if llm else 0.2,
            max_tokens=getattr(llm, "max_tokens", 800) if llm else 800,
            cache=getattr(llm, "cache", True) if llm else True,
            accept_automatically=getattr(llm, "accept_automatically", False)
            if llm
            else False,
            fail_on_error=getattr(llm, "fail_on_error", False) if llm else False,
            prompt_release_notes_file=getattr(llm, "prompt_release_notes_file", None)
            if llm
            else None,
            system_prompt_file=getattr(llm, "system_prompt_file", None)
            if llm
            else None,
        )
