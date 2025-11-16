from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProjectConfig:
    """Project configuration (type, tag prefix, native tools)."""

    type: str = "auto"  # auto|poetry|setuptools|npm
    tag_prefix: str = "v"
    use_native: bool = True


@dataclass
class VersionConfig:
    """Version strategy configuration."""

    strategy: str = "auto"
    since: str = ""
    to: str = "HEAD"
    # Source for determining the current version used as bump base
    # Options: "file" (read from project files), "local_tag" (latest local tag),
    # "remote_tag" (latest tag on remote), "auto" (choose newer between file and latest tag)
    source: str = "file"


@dataclass
class PreReleaseConfig:
    """Pre-release configuration."""

    enabled: bool = False
    default_channel: str = "rc"
    auto_increment: bool = True
    reset_on_bump: bool = True
    apply: List[str] = field(default_factory=lambda: ["develop", "release/*"])
    block: List[str] = field(default_factory=lambda: ["main", "master", "hotfix/*"])


@dataclass
class ChangeLogConfig:
    """Changelog configuration."""

    enabled: bool = False
    file: str = "CHANGELOG.md"
    mode: str = (
        "auto"  # 'auto' to derive from git commits; 'notes' to only include user notes
    )


@dataclass
class AutoGenNotesConfig:
    """Auto-generated release notes configuration."""

    enabled: bool = False
    include_diff: bool = True
    always_diff_types: List[str] = field(default_factory=lambda: ["feat"])
    max_commits: int = 200
    mode: str = "auto"


@dataclass
class ReleaseConfig:
    """Consolidated release configuration."""

    create_commit: bool = True
    create_tag: bool = True
    push: bool = False
    version_targets: List[str] = field(default_factory=list)
    change_log_file: str = "CHANGELOG.md"
    allow_dirty: bool = False
    version: VersionConfig = field(default_factory=VersionConfig)
    pre_release: PreReleaseConfig = field(default_factory=PreReleaseConfig)
    change_log: ChangeLogConfig = field(default_factory=ChangeLogConfig)
    auto_gen_notes: AutoGenNotesConfig = field(default_factory=AutoGenNotesConfig)


@dataclass
class LlmConfig:
    """LLM (Language Model) configuration."""

    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.2
    max_tokens: int = 2500
    cache: bool = True
    accept_automatically: bool = False
    fail_on_error: bool = False
    # Optional custom prompt files
    prompt_release_notes_file: Optional[str] = None
    system_prompt_file: Optional[str] = None


@dataclass
class HooksConfig:
    """Hooks configuration."""

    pre_bump: List[str] = field(default_factory=list)
    post_bump: List[str] = field(default_factory=list)


@dataclass
class CommitLintConfig:
    """Commit lint configuration."""

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
class CommitGenConfig:
    """Commit generation configuration."""

    history_commits: int = 10
    demote_feat_if_similar: bool = True
    allow_scope: bool = False


@dataclass
class BumpRulesConfig:
    """Bump rules configuration (branch-based gating)."""

    apply: List[str] = field(default_factory=list)
    block: List[str] = field(default_factory=list)


@dataclass
class ProviderConfig:
    """Provider-specific configuration."""

    # Can be extended for different providers
    poetry: Dict[str, any] = field(default_factory=dict)
    npm: Dict[str, any] = field(default_factory=dict)
    setuptools: Dict[str, any] = field(default_factory=dict)


@dataclass
class AppConfig:
    """Main application configuration."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    release: ReleaseConfig = field(default_factory=ReleaseConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    commit_lint: CommitLintConfig = field(default_factory=CommitLintConfig)
    commit_gen: CommitGenConfig = field(default_factory=CommitGenConfig)
    bump_rules: BumpRulesConfig = field(default_factory=BumpRulesConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)

    # Resolved locations
    config_path: Optional[str] = None

    # Backward compatibility properties (deprecated)
    @property
    def defaults(self):
        """Deprecated: Use release.create_commit, release.create_tag, release.push instead."""

        class _Defaults:
            def __init__(self, release):
                self.commit = release.create_commit
                self.tag = release.create_tag
                self.push = release.push

        return _Defaults(self.release)

    @property
    def ai(self):
        """Deprecated: Use llm instead."""
        return self.llm

    @property
    def changelog(self):
        """Deprecated: Use release.change_log instead."""
        return self.release.change_log

    @property
    def pre_release(self):
        """Deprecated: Use release.pre_release instead."""
        return self.release.pre_release

    @property
    def files(self):
        """Deprecated: Use release.version_targets instead."""
        return self.release.version_targets

    @property
    def safety(self):
        """Deprecated: Use release.allow_dirty instead."""

        class _Safety:
            def __init__(self, release):
                self.allow_dirty = release.allow_dirty

        return _Safety(self.release)
