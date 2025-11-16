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
class CommitLintConfig:
    enabled: bool = True
    types: List[str] = field(
        default_factory=lambda: [
            "feat",
            "fix",
            "docs",
            "chore",
            "refactor",
            "perf",
            "test",
            "build",
            "ci",
            "revert",
            "style",
        ]
    )
    require_scope: bool = False
    scopes: List[str] = field(default_factory=list)
    scope_pattern: Optional[str] = None
    subject_max_length: int = 100
    allow_bang: bool = True
    allow_breaking_footer: bool = True
    require_ticket: bool = False
    ticket_pattern: Optional[str] = None
    skip_merge_commits: bool = True
    skip_revert_commits: bool = True


@dataclass
class AppConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    pre_release: PreReleaseConfig = field(default_factory=PreReleaseConfig)
    bump_rules: BumpRulesConfig = field(default_factory=BumpRulesConfig)
    changelog: ChangelogConfig = field(default_factory=ChangelogConfig)
    commit_lint: CommitLintConfig = field(default_factory=CommitLintConfig)
    
    @dataclass
    class CommitGenConfig:
        history_commits: int = 10
        demote_feat_if_similar: bool = True
        allow_scope: bool = False

    commit_gen: "AppConfig.CommitGenConfig" = field(default_factory=CommitGenConfig)
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
        always_diff_types: List[str] = field(default_factory=list)
        cache: bool = True
        accept_automatically: bool = False
        fail_on_error: bool = False
        always_diff_types: Optional[List[str]] = None

    ai: "AppConfig.AiSettings" = field(default_factory=AiSettings)
    files: List[str] = field(default_factory=list)
    # Resolved locations
    config_path: Optional[str] = None
