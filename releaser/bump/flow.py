from __future__ import annotations

import datetime
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

from releaser.console import console, logger, prompt_choice, prompt_confirmation, prompt_input
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
        msg = f"chore(release): {tag_name}"
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
    if not bump_type and not manual and not do_finalize:
        # Interactive selection
        bt, manual_v = _interactive_pick_bump2(current_version, tag_prefix)
        interactive = True
        if bt == "manual":
            manual = manual_v
        else:
            bump_type = bt

    # Interactive: choose release line if not specified by flags
    if interactive and not do_pre and not do_finalize:
        options = ["Stable release"]
        # Finalize only if current version is pre-release
        is_pre_now = parse(current_version).pre is not None
        pre_allowed, pre_reason, _channel = check_prerelease_allowed(cfg)
        if pre_allowed:
            options.append("Pre-release")
        else:
            options.append(f"Pre-release (disabled: {pre_reason})")
        if is_pre_now:
            options.append("Finalize pre-release to stable")

        choice = prompt_choice("Select release line", options, default=options[0])
        if choice.startswith("Pre-release ") and not pre_allowed:
            logger.warning("Pre-release not allowed by branch rules; using stable release")
        elif choice.startswith("Pre-release"):
            do_pre = True
        elif choice.startswith("Finalize"):
            do_finalize = True

    if do_finalize:
        target_version = finalize(current_version)
    elif manual:
        target_version = manual.strip()
    else:
        base = parse(current_version).base()
        base_next = bump_base(base, bump_type or _recommend_bump_type())
        if do_pre:
            # Check pre-release rules
            pre_allowed, pre_reason, channel = check_prerelease_allowed(cfg)
            if not pre_allowed:
                logger.error(pre_reason or "Pre-release not allowed")
                return 1
            target_version = apply_prerelease(
                base_next,
                previous_version=current_version,
                channel=channel,
                auto_increment=cfg.pre_release.auto_increment,
            )
        else:
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

    # Show plan
    logger.info(f"Target version: {tag_prefix}{target_version}")
    if notes_text:
        logger.info("Release notes: (will be added to commit and tag)")
        console.print(notes_text)

    # Apply changes
    files_to_add: list[str] = []

    if getattr(args, "changelog", False):
        changelog_path = getattr(args, "changelog_file", None) or "CHANGELOG.md"
        if not dry_run:
            append_changelog(
                changelog_path,
                tag_name,
                datetime.date.today().isoformat(),
                notes_text,
            )
            files_to_add.append(changelog_path)
        else:
            logger.info(f"Would update changelog: {changelog_path}")

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
    """Safer variant avoiding nested quotes in f-strings during patching."""
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
    labels = []
    for key, label in option_specs:
        if key == recommended:
            labels.append(f"{label} [recommended]")
        else:
            labels.append(label)
    choice_label = prompt_choice("Select bump type", labels, default=labels[0])
    idx = labels.index(choice_label)
    key = option_specs[idx][0]
    if key == "manual":
        manual = prompt_input("Enter version (e.g., 1.2.3)")
        return "manual", manual
    if key == "cancel":
        raise SystemExit(0)
    return key, None


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
