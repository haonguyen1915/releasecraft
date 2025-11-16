from __future__ import annotations

import datetime
import subprocess
import configparser
import re
from pathlib import Path
import unicodedata
from dataclasses import dataclass
from typing import Optional, Tuple

from releaser.console import (
    console,
    logger,
    bordered,
    prompt_choice,
    prompt_confirmation,
    prompt_input,
)
from releaser.config.load import load_config
from releaser.config.model import AppConfig
from releaser.bump import providers
from releaser.bump.semver import apply_prerelease, bump_base, finalize, parse
from releaser.bump.rules import check_bump_allowed, check_prerelease_allowed
from releaser.bump.notes import normalize_notes, read_notes_from_editor
from releaser.drafter import utils as git_utils
from releaser.ai.generator import generate_release_notes_with_fallback


@dataclass
class BumpArgs:
    manual: Optional[str] = None
    bump_type: Optional[str] = None  # major|minor|patch
    pre: bool = False
    finalize: bool = False
    dry_run: bool = False
    push: bool = False
    no_commit: bool = False
    no_tag: bool = False
    config: Optional[str] = None
    notes: Optional[str] = None
    notes_file: Optional[str] = None
    changelog: bool = False
    changelog_file: Optional[str] = None


class _Exit(Exception):
    """Internal control-flow exception to unify early exits in run()."""

    def __init__(self, code: int) -> None:
        super().__init__(str(code))
        self.code = code


def _git_commit_tag_push(
    files_to_add: list[str],
    tag_name: str,
    notes: str,
    do_commit: bool,
    do_tag: bool,
    do_push: bool,
) -> None:
    if do_commit:
        subprocess.run(["git", "add", *files_to_add], check=False)
        # Improved commit subject for clarity
        msg = f"chore(release): bump version to {tag_name}"
        if notes:
            msg += f"\n\n{notes}"
        subprocess.run(["git", "commit", "-m", msg], check=True)

    if do_tag:
        tag_msg = notes or tag_name
        subprocess.run(["git", "tag", "-a", tag_name, "-m", tag_msg], check=True)

    if do_push:
        # Determine if an upstream is already configured
        upstream_ref: str | None = None
        try:
            upstream_ref = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                stderr=subprocess.STDOUT,
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            upstream_ref = None

        if upstream_ref:
            # Upstream exists; regular push then ensure tags are sent
            subprocess.run(["git", "push"], check=True)
            if do_tag:
                # Prefer follow-tags; fall back to --tags for broader compatibility
                try:
                    subprocess.run(["git", "push", "--follow-tags"], check=True)
                except subprocess.CalledProcessError:
                    subprocess.run(["git", "push", "--tags"], check=True)
        else:
            # No upstream; set upstream on first push
            current_branch = subprocess.check_output(
                ["git", "branch", "--show-current"], text=True
            ).strip()
            if not current_branch:
                raise subprocess.CalledProcessError(1, "git branch --show-current")

            remotes = (
                subprocess.check_output(["git", "remote"], text=True)
                .strip()
                .splitlines()
            )
            remote = (
                "origin" if "origin" in remotes else (remotes[0] if remotes else None)
            )
            if not remote:
                # Surface a git-like error to be handled by caller
                raise subprocess.CalledProcessError(1, "git push")

            subprocess.run(["git", "push", "-u", remote, current_branch], check=True)
            if do_tag:
                # Push only the newly created tag explicitly
                subprocess.run(["git", "push", remote, tag_name], check=True)


def _read_notes_from_flags(notes: Optional[str], notes_file: Optional[str]) -> str:
    if notes_file:
        try:
            with open(notes_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            logger.warning(f"Could not read notes file: {notes_file}")
    if notes:
        return notes.replace("\\n", "\n").strip()
    return ""


def _recommend_bump_type() -> str:
    # Use commit history to recommend (major/minor/patch)
    commits = git_utils.get_commits_since_tag(git_utils.get_latest_tag())
    try:
        return git_utils.determine_version_bump(commits)  # type: ignore[attr-defined]
    except Exception:
        return "patch"


def _interactive_pick_bump(
    current_v: str, tag_prefix: str
) -> Tuple[str, Optional[str]]:
    recommended = _recommend_bump_type()
    base = parse(current_v).base()
    options = [
        ("patch", f"Patch → {tag_prefix}{bump_base(base, 'patch')}"),
        ("minor", f"Minor → {tag_prefix}{bump_base(base, 'minor')}"),
        ("major", f"Major → {tag_prefix}{bump_base(base, 'major')}"),
        ("manual", "Manual → enter exact version"),
        ("cancel", "Cancel"),
    ]
    # Render choices with recommendation
    labels = []
    for key, label in options:
        if key == recommended:
            labels.append(f"{label} [recommended]")
        else:
            labels.append(label)
    choice_label = prompt_choice("Select bump type", labels, default=labels[0])
    idx = labels.index(choice_label)
    key = options[idx][0]
    if key == "manual":
        manual = prompt_input("Enter version (e.g., 1.2.3)")
        return "manual", manual
    if key == "cancel":
        raise SystemExit(0)
    return key, None


def _run_impl(args) -> int:
    try:
        # Load config
        cfg: AppConfig = load_config(getattr(args, "config", None))

        # Evaluate bump rules
        allowed, reason = check_bump_allowed(cfg)
        if not allowed:
            logger.error(reason or "Bump not allowed")
            raise _Exit(1)

        # Disallow bump if working tree has uncommitted changes
        # Skip check for dry-run or non-git directories
        try:
            repo_present = Path(".git").exists()
            if not getattr(args, "dry_run", False) and repo_present:
                if git_utils.has_uncommitted_changes():
                    if cfg.release.allow_dirty:
                        logger.warning(
                            "Uncommitted changes detected; continuing due to release.allow_dirty=true"
                        )
                    else:
                        logger.warning(
                            "Uncommitted changes detected. Please commit or stash your changes before releasing."
                        )
                        raise _Exit(1)
        except Exception:
            # If the check fails unexpectedly, be safe and abort only when not dry-run
            if not getattr(args, "dry_run", False):
                logger.warning(
                    "Could not verify clean working tree; aborting release for safety"
                )
                raise _Exit(1)

    except _Exit as exc:
        return exc.code

    # Detect provider (Poetry first)
    provider = providers.detect_provider(cwd=".")
    if not provider:
        logger.error(
            "No compatible provider detected (Poetry expected). Ensure pyproject.toml exists."
        )
        raise _Exit(1)

    tag_prefix = cfg.project.tag_prefix or "v"

    # Determine current version source
    version_source = getattr(args, "version_source", None) or getattr(
        cfg.release.version, "source", "file"
    )

    def _strip_prefix(tag: str) -> str:
        if not tag:
            return tag
        return (
            tag[len(tag_prefix) :] if tag_prefix and tag.startswith(tag_prefix) else tag
        )

    # Always read file version for fallback and for writing later
    file_version = provider.read_version()
    current_version = file_version

    # Optionally select from tag sources
    if version_source == "local_tag":
        tag = git_utils.get_latest_tag()
        if tag:
            current_version = _strip_prefix(tag)
            logger.info(f"Using current version from latest local tag: {tag}")
        else:
            logger.warning("No local tags found; falling back to file version")
    elif version_source == "remote_tag":
        tag = git_utils.get_latest_remote_tag(prefix=tag_prefix)
        if tag:
            current_version = _strip_prefix(tag)
            logger.info(f"Using current version from latest remote tag: {tag}")
        else:
            logger.warning("No remote tags found; falling back to file version")
    elif version_source == "auto":
        tag = git_utils.get_latest_tag()
        if not tag:
            # try remote as a backup
            tag = git_utils.get_latest_remote_tag(prefix=tag_prefix)
        tag_version = _strip_prefix(tag) if tag else ""
        try:
            fa = parse(file_version)
            ta = parse(tag_version) if tag_version else None
            fkey = (fa.major, fa.minor, fa.patch, 1 if not fa.pre else 0)
            tkey = (
                (ta.major, ta.minor, ta.patch, 1 if not ta.pre else 0)
                if ta
                else (-1, -1, -1, -1)
            )
            if tkey > fkey:
                current_version = tag_version
                logger.info(f"Auto-selected current version from tag: {tag}")
        except Exception:
            # If parsing fails, keep file version
            pass

    logger.info(
        f"Detected provider: poetry • Current version: {tag_prefix}{current_version}"
    )

    # Decide bump type / target version
    bump_type = getattr(args, "type", None)
    manual = getattr(args, "manual", None)
    do_pre = bool(getattr(args, "pre", False))
    do_finalize = bool(getattr(args, "finalize", False))
    dry_run = bool(getattr(args, "dry_run", False))

    target_version = None

    interactive = False
    if not bump_type and not manual and not do_finalize and not do_pre:
        # Decide pre-release capability
        pre_allowed, pre_reason, channel = check_prerelease_allowed(cfg)
        is_pre_now = parse(current_version).pre is not None
        # Interactive numeric selection that includes pre-release choices when allowed
        bt, manual_v, pre_sel, finalize_sel = _interactive_pick_bump3(
            current_version,
            tag_prefix,
            pre_allowed,
            channel,
            cfg.release.pre_release.auto_increment,
            is_pre_now,
        )
        interactive = True
        do_pre = pre_sel or do_pre
        do_finalize = finalize_sel or do_finalize
        if bt == "manual":
            manual = manual_v
        else:
            bump_type = bt

    if do_finalize:
        target_version = finalize(current_version)
    elif manual:
        target_version = manual.strip()
    else:
        current_base = parse(current_version).base()
        # Determine base to apply
        if do_pre:
            # Pre-release: if no explicit bump type, use current base. Otherwise bump base then apply pre.
            base_for_pre = (
                bump_base(current_base, bump_type) if bump_type else current_base
            )
            # Check pre-release rules
            pre_allowed, pre_reason, channel = check_prerelease_allowed(cfg)
            if not pre_allowed:
                logger.error(pre_reason or "Pre-release not allowed")
                return 1
            target_version = apply_prerelease(
                base_for_pre,
                previous_version=current_version,
                channel=channel,
                auto_increment=cfg.release.pre_release.auto_increment,
            )
        else:
            base_next = bump_base(current_base, bump_type or _recommend_bump_type())
            target_version = base_next

    tag_name = f"{tag_prefix}{target_version}"

    # Notes handling
    notes_text = _read_notes_from_flags(
        getattr(args, "notes", None), getattr(args, "notes_file", None)
    )

    # AI-powered release notes generation
    if (
        not notes_text
        and cfg.release.auto_gen_notes.enabled
        and not getattr(args, "no_commit", False)
        and not getattr(args, "no_tag", False)
    ):
        logger.info("AI is enabled, generating release notes...")
        try:
            # Get the latest git tag for the previous version
            previous_tag = git_utils.get_latest_tag()
            if not previous_tag:
                logger.warning(
                    "No previous tag found, getting all commits from repository start"
                )
                # Get the first commit in the repository
                result = subprocess.run(
                    ["git", "rev-list", "--max-parents=0", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    previous_tag = result.stdout.strip()
                else:
                    # Ultimate fallback: use HEAD itself (will show 0 commits but won't crash)
                    logger.warning("Could not determine first commit, using HEAD")
                    previous_tag = "HEAD"

            # Build AiConfig from app config (combines LLM and auto_gen_notes settings)
            from releaser.ai.config import AiConfig

            ai_config = AiConfig.from_app_config(cfg)

            ai_notes = generate_release_notes_with_fallback(
                config=ai_config,
                repo_path=Path.cwd(),
                current_version=str(target_version),
                previous_version=previous_tag,
            )

            if ai_notes:
                # Show AI-generated notes
                bordered.create_bordered_content(
                    ai_notes,
                    title="AI-GENERATED RELEASE NOTES",
                    dry_run=False,
                )

                # Allow review/editing unless auto-accept is enabled
                if cfg.llm.accept_automatically:
                    logger.info(
                        "Auto-accepting AI-generated notes (accept_automatically=True)"
                    )
                    notes_text = ai_notes
                else:
                    # Ask user if they want to use, edit, or reject
                    choice = prompt_choice(
                        "How would you like to proceed?",
                        [
                            "Use AI notes as-is",
                            "Edit AI notes in editor",
                            "Reject and write manually",
                        ],
                        default="Use AI notes as-is",
                    )

                    if choice == "Use AI notes as-is":
                        notes_text = ai_notes
                    elif choice == "Edit AI notes in editor":
                        # Open in editor with AI notes pre-filled
                        notes_text = read_notes_from_editor(initial_text=ai_notes)
                    # else: Reject, will fall through to manual prompt
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            if cfg.llm.fail_on_error:
                raise
            logger.warning("Falling back to manual release notes entry")

    # Manual notes entry (if still no notes)
    if (
        not notes_text
        and not getattr(args, "no_commit", False)
        and not getattr(args, "no_tag", False)
    ):
        # Simple Yes/No flow; Yes = type inline multi-line, finish with two blank lines
        if prompt_confirmation("Add release notes?", default=False):
            notes_text = _prompt_multiline_notes()

    notes_text = normalize_notes(notes_text)

    # Auto apply changelog from config when enabled (preview even in dry-run)
    if not getattr(args, "changelog", False) and cfg.release.change_log.enabled:
        setattr(args, "changelog", True)
        if not getattr(args, "changelog_file", None):
            setattr(
                args, "changelog_file", cfg.release.change_log.file or "CHANGELOG.md"
            )

    # Interactive: Ask to update changelog if not specified via flags nor config
    if (
        interactive
        and not getattr(args, "changelog", False)
        and not dry_run
        and not cfg.release.change_log.enabled
    ):
        if prompt_confirmation(
            "Update CHANGELOG.md with this release?", default=bool(notes_text)
        ):
            setattr(args, "changelog", True)
            default_path = getattr(args, "changelog_file", None) or "CHANGELOG.md"
            path = prompt_input("Changelog path", default=default_path)
            setattr(args, "changelog_file", path)

    # Show plan
    logger.info(f"Target version: {tag_prefix}{target_version}")
    if notes_text:
        logger.info("Release notes: (will be added to commit and tag)")
        console.print(notes_text)

    # Apply changes
    files_to_add: list[str] = []

    if getattr(args, "changelog", False):
        changelog_path = getattr(args, "changelog_file", None) or "CHANGELOG.md"
        # Prepare changelog content for preview or write
        changelog_date = datetime.date.today().isoformat()
        changelog_content = _build_changelog_content(
            cfg, current_version, tag_prefix, target_version, changelog_date, notes_text
        )

        if not dry_run:
            # Use the fully rendered content with typed sections
            from releaser.bump.notes import append_changelog_block as _append_block

            _append_block(
                changelog_path,
                changelog_content,
            )
            files_to_add.append(changelog_path)
        else:
            logger.info(f"Would update changelog: {changelog_path}")
            # Show a bordered preview of the content that would be added
            # For first-time creation, include a title
            preview = changelog_content
            if not Path(changelog_path).exists():
                preview = "# Changelog\n\n" + preview
            bordered.create_bordered_content(
                preview,
                title="CHANGELOG PREVIEW",
                dry_run=True,
            )

    # Decide actions (interactive prompt if flags not explicitly steering)
    do_commit = not getattr(args, "no_commit", False)
    do_tag = not getattr(args, "no_tag", False)
    do_push = bool(getattr(args, "push", False))

    if (
        interactive
        and not dry_run
        and not getattr(args, "no_commit", False)
        and not getattr(args, "no_tag", False)
        and not getattr(args, "push", False)
    ):
        do_commit = prompt_confirmation("Commit changes?", default=True)
        do_tag = prompt_confirmation("Create annotated tag?", default=True)
        do_push = prompt_confirmation("Push to remote?", default=False)

    if dry_run:
        logger.info("Dry-run: no file changes, no commit/tag/push performed")
        return 0

    # Write version to file(s) after confirming not dry-run
    updated_file = provider.write_version(
        target_version, use_native=cfg.project.use_native
    )
    files_to_add.append(updated_file)

    # Update additional files from config (e.g., pkg/__init__.py:__version__, setup.cfg:metadata.version)
    logger.debug(f"Additional file targets: {cfg.release.version_targets}")
    for entry in cfg.release.version_targets or []:
        try:
            path, selector = entry.split(":", 1)
        except ValueError:
            continue
        _update_additional_file_version(
            path.strip(), selector.strip(), target_version, files_to_add
        )
        logger.debug(f"Updated file target: {entry}")

    try:
        _git_commit_tag_push(
            files_to_add, tag_name, notes_text, do_commit, do_tag, do_push
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")
        raise _Exit(1)

    logger.success(f"Bumped to {tag_name}")
    return 0


def _interactive_pick_bump2(
    current_v: str, tag_prefix: str
) -> Tuple[str, Optional[str]]:
    """Numeric selection UI for bump type with per-line options.

    Shows options as a numbered list:
      1) Patch → vX.Y.(Z+1)
      2) Minor → vX.(Y+1).0
      3) Major → v(X+1).0.0
      4) Manual → enter exact version
      5) Cancel
    The recommended option (based on commit history) is annotated.
    """
    recommended = _recommend_bump_type()
    base = parse(current_v).base()
    patch_target = f"{tag_prefix}{bump_base(base, 'patch')}"
    minor_target = f"{tag_prefix}{bump_base(base, 'minor')}"
    major_target = f"{tag_prefix}{bump_base(base, 'major')}"

    option_specs = [
        ("patch", f"Patch → {patch_target}"),
        ("minor", f"Minor → {minor_target}"),
        ("major", f"Major → {major_target}"),
        ("manual", "Manual → enter exact version"),
        ("cancel", "Cancel"),
    ]

    console.print("\n[bold]Select bump type[/bold]")
    for i, (key, label) in enumerate(option_specs, start=1):
        suffix = " [recommended]" if key == recommended else ""
        console.print(f"  {i}) {label}{suffix}")

    # Prompt until a valid number is chosen
    while True:
        choice = prompt_input("Enter choice number", default="1").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(option_specs):
                key = option_specs[idx - 1][0]
                if key == "manual":
                    manual = prompt_input("Enter version (e.g., 1.2.3)")
                    return "manual", manual
                if key == "cancel":
                    raise SystemExit(0)
                return key, None
        console.print("[yellow]Please enter a valid number from the list[/yellow]")


def _interactive_pick_bump3(
    current_v: str,
    tag_prefix: str,
    pre_allowed: bool,
    channel: str,
    auto_increment: bool,
    is_pre_now: bool,
) -> Tuple[Optional[str], Optional[str], bool, bool]:
    """Numeric selection UI combining bump type and release line.

    Returns: (bump_type or 'manual', manual_value, do_pre, do_finalize)
    """
    base = parse(current_v).base()
    patch_target = f"{tag_prefix}{bump_base(base, 'patch')}"
    minor_target = f"{tag_prefix}{bump_base(base, 'minor')}"
    major_target = f"{tag_prefix}{bump_base(base, 'major')}"

    # Pre-release preview applies to current base (no bump)
    pre_preview = f"{tag_prefix}{apply_prerelease(base, previous_version=current_v, channel=channel, auto_increment=auto_increment)}"

    entries: list[Tuple[str, str, bool, bool]] = []
    # (bump_type/manual, label, do_pre, do_finalize)
    entries.append(("patch", f"Patch → {patch_target}", False, False))
    entries.append(("minor", f"Minor → {minor_target}", False, False))
    entries.append(("major", f"Major → {major_target}", False, False))
    if pre_allowed:
        entries.append((None, f"Pre-release ({channel}) → {pre_preview}", True, False))
    if is_pre_now:
        entries.append(
            (
                None,
                f"Finalize current pre-release → {tag_prefix}{finalize(current_v)}",
                False,
                True,
            )
        )
    entries.append(("manual", "Manual → enter exact version", False, False))
    entries.append((None, "Cancel", False, True))

    # Print list
    console.print("\n[bold]Select bump type[/bold]")
    for i, (_k, label, _p, _f) in enumerate(entries, start=1):
        console.print(f"  {i}) {label}")

    # Choose
    while True:
        choice = prompt_input("Enter choice number", default="1").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(entries):
                k, _label, p, fz = entries[idx - 1]
                if _label.startswith("Cancel"):
                    raise SystemExit(0)
                if k == "manual":
                    manual = prompt_input("Enter version (e.g., 1.2.3)")
                    return "manual", manual, False, False
                return k, None, p, fz
        console.print("[yellow]Please enter a valid number from the list[/yellow]")


def _build_changelog_content(
    cfg: AppConfig,
    current_version: str,
    tag_prefix: str,
    new_version: str,
    date_str: str,
    notes_text: str,
) -> str:
    tag_name = f"{tag_prefix}{new_version}"
    header = f"## {tag_name} – {date_str}\n\n"

    body = ""
    # If auto mode and git repo present, derive content from commits
    repo_present = Path(".git").exists()
    if cfg.release.change_log.mode.lower() == "auto" and repo_present:
        try:
            previous_tag = git_utils.get_latest_tag()
            entries = git_utils.get_commits_since_tag(previous_tag)
            sections: dict[str, list[str]] = {
                "feat": [],
                "fix": [],
                "hotfix": [],
                "docs": [],
                "refactor": [],
                "perf": [],
                "test": [],
                "ci": [],
                "build": [],
                "style": [],
                "revert": [],
                "chore": [],
                "other": [],
            }
            for line in entries or []:
                if not line.strip():
                    continue
                parts = line.split("|", 2)
                sha = parts[0] if parts else ""
                subject = parts[1] if len(parts) > 1 else line
                ctype = git_utils.parse_commit_type(subject)
                ctype = (ctype or "other").lower()
                if ctype not in sections:
                    ctype = "other"
                bullet = f"- {subject.strip()} ({sha[:7]})"
                sections[ctype].append(bullet)

            section_titles = [
                ("feat", "Features"),
                ("fix", "Bug Fixes"),
                ("hotfix", "Hotfixes"),
                ("docs", "Documentation"),
                ("refactor", "Refactoring"),
                ("perf", "Performance"),
                ("test", "Tests"),
                ("ci", "CI"),
                ("build", "Build"),
                ("style", "Styles"),
                ("revert", "Reverts"),
                ("chore", "Chores"),
                ("other", "Other"),
            ]
            for key, title in section_titles:
                items = [b for b in sections.get(key, []) if b.strip()]
                if items:
                    body += f"### {title}\n\n" + "\n".join(items) + "\n\n"

            # Append contributors and compare link
            try:
                contributors = git_utils.get_contributors(previous_tag)
                contributors = _normalize_contributors(contributors)
            except Exception:
                contributors = ""
            try:
                repo_url = git_utils.get_repo_url()
            except Exception:
                repo_url = ""
            if contributors:
                body += f"**Contributors:** {contributors}\n\n"
            if repo_url and previous_tag:
                body += f"**Compare changes:** [{previous_tag}...{tag_name}]({repo_url}/-/compare/{previous_tag}...{tag_name})\n\n"
        except Exception:
            # Fallback silently to notes only
            body = ""

    # Include user-provided notes (top) if present
    if notes_text:
        body = f"### Release Notes\n\n{notes_text.strip()}\n\n" + body

    return header + body


def _normalize_contributors(contributors_line: str) -> str:
    """Deduplicate contributors ignoring case/diacritics and whitespace.

    Input: "@Name A, @name a, @Náme A" -> "@Name A"
    Preserves the first encountered display name for each normalized key.
    """
    if not contributors_line:
        return ""
    parts = [p.strip() for p in contributors_line.split(",") if p.strip()]
    seen = {}
    order = []
    for p in parts:
        disp = p
        if disp.startswith("@"):
            disp = disp[1:]
        key = " ".join(disp.strip().split())
        key = unicodedata.normalize("NFKD", key)
        key = "".join(ch for ch in key if not unicodedata.combining(ch))
        key = key.casefold()
        if key not in seen:
            seen[key] = disp
            order.append(key)
    return ", ".join(f"@{seen[k]}" for k in order)


def _update_additional_file_version(
    path_str: str, selector: str, version: str, files_to_add: list[str]
) -> None:
    p = Path(path_str)
    if not p.exists():
        return
    # Python __init__.py: __version__
    if p.suffix == ".py" and selector == "__version__":
        content = p.read_text()
        if re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", content, flags=re.M):
            content = re.sub(
                r"^__version__\s*=\s*['\"]([^'\"]+)['\"]",
                f"__version__ = '{version}'",
                content,
                flags=re.M,
            )
        else:
            if not content.endswith("\n"):
                content += "\n"
            content += f"__version__ = '{version}'\n"
        p.write_text(content, encoding="utf-8")
        files_to_add.append(str(p))
        return

    # setup.cfg: metadata.version
    if p.name == "setup.cfg" and selector == "metadata.version":
        cp = configparser.ConfigParser()
        cp.read(p)
        if not cp.has_section("metadata"):
            cp.add_section("metadata")
        cp.set("metadata", "version", version)
        with p.open("w", encoding="utf-8") as f:
            cp.write(f)
        files_to_add.append(str(p))
        return


def _prompt_multiline_notes() -> str:
    logger.info("Enter release notes (finish with two empty lines):")
    lines: list[str] = []
    empty_line_count = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            empty_line_count += 1
            if empty_line_count >= 2:
                if lines and lines[-1] == "":
                    lines.pop()
                break
            lines.append(line)
        else:
            empty_line_count = 0
            lines.append(line)
    return "\n".join(lines).strip()


def run(args) -> int:
    """Wrapper that normalizes early exits from `_run_impl`.

    Converts internal `_Exit` exceptions to integer exit codes for the CLI.
    """
    try:
        return _run_impl(args)
    except _Exit as exc:
        return exc.code
