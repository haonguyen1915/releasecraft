from __future__ import annotations

import datetime
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

from releaser.console import console, logger, bordered, prompt_choice, prompt_confirmation, prompt_input
from releaser.config.load import load_config
from releaser.config.model import AppConfig
from releaser.bump import providers
from releaser.bump.semver import apply_prerelease, bump_base, finalize, parse
from releaser.bump.rules import check_bump_allowed, check_prerelease_allowed
from releaser.bump.notes import append_changelog, normalize_notes, read_notes_from_editor
from releaser.drafter import utils as git_utils
import configparser
import re
from pathlib import Path


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


def _git_commit_tag_push(files_to_add: list[str], tag_name: str, notes: str, do_commit: bool, do_tag: bool, do_push: bool) -> None:
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
        subprocess.run(["git", "push"], check=True)
        if do_tag:
            subprocess.run(["git", "push", "--tags"], check=True)


def _read_notes_from_flags(notes: Optional[str], notes_file: Optional[str]) -> str:
    if notes_file:
        try:
            with open(notes_file, "r") as f:
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


def _interactive_pick_bump(current_v: str, tag_prefix: str) -> Tuple[str, Optional[str]]:
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


def run(args) -> int:
    # Load config
    cfg: AppConfig = load_config(getattr(args, "config", None))

    # Evaluate bump rules
    allowed, reason = check_bump_allowed(cfg)
    if not allowed:
        logger.error(reason or "Bump not allowed")
        return 1

    # Disallow bump if working tree has uncommitted changes
    # Skip check for dry-run or non-git directories
    from pathlib import Path as _Path
    try:
        repo_present = _Path(".git").exists()
        if not getattr(args, "dry_run", False) and repo_present:
            if git_utils.has_uncommitted_changes():
                if getattr(cfg, "safety", None) and getattr(cfg.safety, "allow_dirty", False):
                    logger.warning("Uncommitted changes detected; continuing due to safety.allow_dirty=true")
                else:
                    logger.warning(
                        "Uncommitted changes detected. Please commit or stash your changes before releasing."
                    )
                    return 1
    except Exception:
        # If the check fails unexpectedly, be safe and abort only when not dry-run
        if not getattr(args, "dry_run", False):
            logger.warning("Could not verify clean working tree; aborting release for safety")
            return 1

    # Detect provider (Poetry first)
    provider = providers.detect_provider(cwd=".")
    if not provider:
        logger.error("No compatible provider detected (Poetry expected). Ensure pyproject.toml exists.")
        return 1

    current_version = provider.read_version()
    tag_prefix = cfg.project.tag_prefix or "v"
    logger.info(f"Detected provider: poetry • Current version: {tag_prefix}{current_version}")

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
            cfg.pre_release.auto_increment,
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
                auto_increment=cfg.pre_release.auto_increment,
            )
        else:
            base_next = bump_base(current_base, bump_type or _recommend_bump_type())
            target_version = base_next

    tag_name = f"{tag_prefix}{target_version}"

    # Notes handling
    notes_text = _read_notes_from_flags(getattr(args, "notes", None), getattr(args, "notes_file", None))
    if not notes_text and not getattr(args, "no_commit", False) and not getattr(args, "no_tag", False):
        # Interactive prompt for release notes
        choice = prompt_choice(
            "Add release notes?",
            ["None", "Write notes (open $EDITOR)", "Read from file"],
            default="None",
        )
        if choice.startswith("Write"):
            notes_text = read_notes_from_editor("")
        elif choice.startswith("Read"):
            path = prompt_input("Path to notes file", default="RELEASE_NOTES.md")
            try:
                with open(path, "r") as f:
                    notes_text = f.read().strip()
            except Exception:
                logger.warning(f"Could not read notes file: {path}")

    notes_text = normalize_notes(notes_text)

    # Auto apply changelog from config when enabled (preview even in dry-run)
    if not getattr(args, "changelog", False) and cfg.changelog.enabled:
        setattr(args, "changelog", True)
        if not getattr(args, "changelog_file", None):
            setattr(args, "changelog_file", cfg.changelog.file or "CHANGELOG.md")

    # Interactive: Ask to update changelog if not specified via flags nor config
    if (
        interactive
        and not getattr(args, "changelog", False)
        and not dry_run
        and not cfg.changelog.enabled
    ):
        if prompt_confirmation("Update CHANGELOG.md with this release?", default=bool(notes_text)):
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
            append_changelog(
                changelog_path,
                tag_name,
                changelog_date,
                notes_text,
            )
            files_to_add.append(changelog_path)
        else:
            logger.info(f"Would update changelog: {changelog_path}")
            # Show a bordered preview of the content that would be added
            bordered.create_bordered_content(
                changelog_content,
                title="CHANGELOG PREVIEW",
                dry_run=True,
            )

    # Decide actions (interactive prompt if flags not explicitly steering)
    do_commit = not getattr(args, "no_commit", False)
    do_tag = not getattr(args, "no_tag", False)
    do_push = bool(getattr(args, "push", False))

    if interactive and not dry_run and not getattr(args, "no_commit", False) and not getattr(args, "no_tag", False) and not getattr(args, "push", False):
        do_commit = prompt_confirmation("Commit changes?", default=True)
        do_tag = prompt_confirmation("Create annotated tag?", default=True)
        do_push = prompt_confirmation("Push to remote?", default=False)

    if dry_run:
        logger.info("Dry-run: no file changes, no commit/tag/push performed")
        return 0

    # Write version to file(s) after confirming not dry-run
    updated_file = provider.write_version(target_version, use_native=cfg.project.use_native)
    files_to_add.append(updated_file)

    # Update additional files from config (e.g., pkg/__init__.py:__version__, setup.cfg:metadata.version)
    logger.debug(f"Additional file targets: {cfg.files}")
    for entry in cfg.files or []:
        try:
            path, selector = entry.split(":", 1)
        except ValueError:
            continue
        _update_additional_file_version(path.strip(), selector.strip(), target_version, files_to_add)
        logger.debug(f"Updated file target: {entry}")

    try:
        _git_commit_tag_push(files_to_add, tag_name, notes_text, do_commit, do_tag, do_push)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")
        return 1

    logger.success(f"Bumped to {tag_name}")
    return 0


def _interactive_pick_bump2(current_v: str, tag_prefix: str) -> Tuple[str, Optional[str]]:
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
    from releaser.bump.semver import apply_prerelease as _apply_pr
    pre_preview = f"{tag_prefix}{_apply_pr(base, previous_version=current_v, channel=channel, auto_increment=auto_increment)}"

    entries: list[Tuple[str, str, bool, bool]] = []
    # (bump_type/manual, label, do_pre, do_finalize)
    entries.append(("patch", f"Patch → {patch_target}", False, False))
    entries.append(("minor", f"Minor → {minor_target}", False, False))
    entries.append(("major", f"Major → {major_target}", False, False))
    if pre_allowed:
        entries.append((None, f"Pre-release ({channel}) → {pre_preview}", True, False))
    if is_pre_now:
        from releaser.bump.semver import finalize as _final
        entries.append((None, f"Finalize current pre-release → {tag_prefix}{_final(current_v)}", False, True))
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
    if cfg.changelog.mode.lower() == "auto" and repo_present:
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


def _update_additional_file_version(path_str: str, selector: str, version: str, files_to_add: list[str]) -> None:
    p = Path(path_str)
    if not p.exists():
        return
    # Python __init__.py: __version__
    if p.suffix == ".py" and selector == "__version__":
        content = p.read_text()
        if re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", content, flags=re.M):
            content = re.sub(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", f"__version__ = '{version}'", content, flags=re.M)
        else:
            if not content.endswith("\n"):
                content += "\n"
            content += f"__version__ = '{version}'\n"
        p.write_text(content)
        files_to_add.append(str(p))
        return

    # setup.cfg: metadata.version
    if p.name == "setup.cfg" and selector == "metadata.version":
        cp = configparser.ConfigParser()
        cp.read(p)
        if not cp.has_section("metadata"):
            cp.add_section("metadata")
        cp.set("metadata", "version", version)
        with p.open("w") as f:
            cp.write(f)
        files_to_add.append(str(p))
        return
