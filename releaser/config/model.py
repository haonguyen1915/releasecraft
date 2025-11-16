from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProjectConfig:
    type: str = "auto"  # auto|poetry|setuptools|npm
    tag_prefix: str = "v"
    use_native: bool = True


@dataclass
class DefaultsConfig:
    commit: bool = True
    tag: bool = True
    push: bool = False


@dataclass
class PreReleaseConfig:
    enabled: bool = False
    default_channel: str = "rc"
    auto_increment: bool = True
    reset_on_bump: bool = True
    apply: List[str] = field(default_factory=list)
    block: List[str] = field(default_factory=list)
    channel_map: Dict[str, str] = field(default_factory=dict)


@dataclass
class BumpRulesConfig:
    apply: List[str] = field(default_factory=list)
    block: List[str] = field(default_factory=list)


@dataclass
class ChangelogConfig:
    enabled: bool = False
    file: str = "CHANGELOG.md"
    mode: str = "auto"  # 'auto' to derive from git commits; 'notes' to only include user notes


@dataclass
class AppConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    pre_release: PreReleaseConfig = field(default_factory=PreReleaseConfig)
    bump_rules: BumpRulesConfig = field(default_factory=BumpRulesConfig)
    changelog: ChangelogConfig = field(default_factory=ChangelogConfig)
    # Safety options (e.g., allow dirty working tree)
    class SafetyConfig:
        allow_dirty: bool = False

    safety: "AppConfig.SafetyConfig" = field(default_factory=SafetyConfig)
    # AI settings (OpenAI + Instructor)
    @dataclass
    class AiSettings:
        enabled: bool = False
        provider: str = "openai"
        model: str = "gpt-4o-mini"
        api_key_env: str = "OPENAI_API_KEY"
        temperature: float = 0.2
        max_tokens: int = 800
        prompt_release_notes_file: Optional[str] = None
        system_prompt_file: Optional[str] = None
        include_diff: bool = False
        max_commits: int = 200
        cache: bool = True
        accept_automatically: bool = False
        fail_on_error: bool = False

    ai: "AppConfig.AiSettings" = field(default_factory=AiSettings)
    files: List[str] = field(default_factory=list)
    # Resolved locations
    config_path: Optional[str] = None
