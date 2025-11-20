from __future__ import annotations

import configparser
import datetime
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import urlparse, quote

import requests

from releaser.ai.generator import generate_release_notes_with_fallback
from releaser.bump import providers
from releaser.bump.notes import normalize_notes, read_notes_from_editor
from releaser.bump.rules import check_bump_allowed, check_prerelease_allowed
from releaser.bump.semver import apply_prerelease, bump_base, finalize, parse
from releaser.config.load import load_config
from releaser.config.model import AppConfig
from releaser.console import (
    bordered,
    console,
    logger,
    prompt_choice,
    prompt_confirmation,
    prompt_input,
)
from releaser.drafter import utils as git_utils


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
    gitlab_release: bool = False
    github_draft_release: bool = False


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
        msg = f"chore: bump version to {tag_name}"
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


def _parse_repo_slug(repo_url: str) -> Optional[str]:
    """Extract the \"owner/repo\" or \"group/project\" slug from a git remote URL.

    Supports SSH and HTTPS remotes, with or without .git suffix.
    """
    if not repo_url:
        return None
    url = repo_url.strip()
    if url.endswith(".git"):
        url = url[: -len(".git")]

    # git@host:owner/repo or ssh://git@host/owner/repo
    if url.startswith("git@"):
        try:
            _user_host, path = url.split(":", 1)
            return path.strip("/")
        except ValueError:
            return None
    if url.startswith("ssh://"):
        try:
            parsed = urlparse(url)
            path = parsed.path or ""
            return path.lstrip("/") or None
        except Exception:
            return None

    # http(s)://host/owner/repo
    try:
        parsed = urlparse(url)
        path = parsed.path or ""
        return path.lstrip("/") or None
    except Exception:
        return None


def _create_github_draft_release(tag_name: str, body: str) -> None:
    """Create a GitHub draft Release for the given tag, best-effort."""
    repo_url = git_utils.get_repo_url()
    if not repo_url:
        logger.warning(
            "Cannot create GitHub draft Release: no git remote URL detected."
        )
        return

    slug = _parse_repo_slug(repo_url)
    if not slug:
        logger.warning(
            f"Cannot create GitHub draft Release: could not parse repository from URL '{repo_url}'."
        )
        return

    parsed = urlparse(repo_url.replace(":", "/"))
    host = (parsed.hostname or "").lower()
    if "github" not in host and "GITHUB_API_URL" not in os.environ:
        logger.warning(
            "Remote does not look like GitHub and GITHUB_API_URL is not set; "
            "skipping GitHub draft Release."
        )
        return

    parts = slug.split("/")
    if len(parts) < 2:
        logger.warning(
            f"Cannot create GitHub draft Release: unexpected repository slug '{slug}'."
        )
        return
    owner, repo = parts[0], parts[1]

    api_base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        logger.warning(
            "GITHUB_TOKEN or GH_TOKEN not set; skipping GitHub draft Release creation."
        )
        return

    url = f"{api_base}/repos/{owner}/{repo}/releases"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "tag_name": tag_name,
        "name": tag_name,
        "body": body or "",
        "draft": True,
        # Mark as pre-release when version contains a hyphen (e.g. 1.0.0-rc.1)
        "prerelease": "-" in tag_name,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as exc:
        logger.error(f"Error while creating GitHub draft Release: {exc}")
        return

    if resp.status_code >= 400:
        logger.error(
            f"Failed to create GitHub draft Release "
            f"({resp.status_code}): {resp.text.strip()}"
        )
    else:
        logger.info("Created GitHub draft Release successfully.")


def _create_gitlab_release(tag_name: str, body: str) -> None:
    """Create a GitLab Release for the given tag, best-effort."""
    repo_url = git_utils.get_repo_url()
    if not repo_url:
        logger.warning("Cannot create GitLab Release: no git remote URL detected.")
        return

    slug = _parse_repo_slug(repo_url)
    if not slug:
        logger.warning(
            f"Cannot create GitLab Release: could not parse project from URL '{repo_url}'."
        )
        return

    parsed = urlparse(repo_url.replace(":", "/"))
    host = (parsed.hostname or "").lower()
    if "gitlab" not in host and "GITLAB_API_URL" not in os.environ:
        logger.warning(
            "Remote does not look like GitLab and GITLAB_API_URL is not set; "
            "skipping GitLab Release."
        )
        return

    api_base = os.environ.get("GITLAB_API_URL", "https://gitlab.com/api/v4").rstrip(
        "/"
    )
    token = os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN")
    if not token:
        logger.warning(
            "GITLAB_TOKEN or CI_JOB_TOKEN not set; skipping GitLab Release creation."
        )
        return

    project_id = quote(slug, safe="")
    url = f"{api_base}/projects/{project_id}/releases"
    headers = {"PRIVATE-TOKEN": token}
    payload = {
        "name": tag_name,
        "tag_name": tag_name,
        "description": body or "",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as exc:
        logger.error(f"Error while creating GitLab Release: {exc}")
        return

    if resp.status_code >= 400:
        logger.error(
            f"Failed to create GitLab Release ({resp.status_code}): "
            f"{resp.text.strip()}"
        )
    else:
        logger.info("Created GitLab Release successfully.")


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
        return git_utils.determine_version_bump(commits)
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


def _run_impl(args: Any) -> int:
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

    target_version: Optional[str] = None

    interactive = False
    # Enable interactive flow only for CLI usage (argparse.Namespace with command="bump")
    interactive_allowed = getattr(args, "command", None) == "bump"
    if interactive_allowed and not bump_type and not manual and not do_finalize:
        # Decide pre-release capability
        pre_allowed, pre_reason, channel = check_prerelease_allowed(cfg)
        is_pre_now = parse(current_version).pre is not None

        if do_pre:
            # Pre-release mode: show options that produce pre-release versions
            if not pre_allowed:
                logger.error(pre_reason or "Pre-release not allowed")
                return 1
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
            elif bt:
                bump_type = bt
        else:
            # Stable mode: interactive numeric bump selection (patch/minor/major/manual)
            bt, manual_v = _interactive_pick_bump2(current_version, tag_prefix)
            interactive = True
            if bt == "manual":
                manual = manual_v
            else:
                bump_type = bt

    if do_finalize:
        target_version = finalize(current_version)
    elif manual:
        target_version = manual.strip()
    else:
        parsed_current = parse(current_version)
        current_base = parsed_current.base()
        if do_pre:
            # Pre-release mode:
            # - From a stable version: bump base (major/minor/patch) then start rc.1.
            # - From an existing pre-release:
            #     * With no bump_type or bump_type == "continue": increment rc on same base.
            #     * With bump_type in {major,minor,patch}: bump base then start new rc.1.
            pre_allowed, pre_reason, channel = check_prerelease_allowed(cfg)
            if not pre_allowed:
                logger.error(pre_reason or "Pre-release not allowed")
                return 1

            is_pre_now = parsed_current.pre is not None

            if is_pre_now:
                # Already on a pre-release
                if not bump_type or bump_type == "continue":
                    # Continue pre-release on the same base (rc.N -> rc.N+1)
                    base_for_pre = current_base
                    previous_version = current_version
                else:
                    # Bump base then start a new pre-release sequence (rc.1)
                    base_for_pre = bump_base(current_base, bump_type)
                    previous_version = None
            else:
                # Stable version: bump base (auto or forced) then start rc.1
                effective_bump_type = bump_type or _recommend_bump_type()
                base_for_pre = bump_base(current_base, effective_bump_type)
                previous_version = None

            target_version = apply_prerelease(
                base_for_pre,
                previous_version=previous_version,
                channel=channel,
                auto_increment=cfg.release.pre_release.auto_increment,
            )
        else:
            # Stable bump (no pre-release)
            effective_bump_type = bump_type or _recommend_bump_type()
            base_next = bump_base(current_base, effective_bump_type)
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
    logger.info(f"Tag to be created: {tag_name}")

    if dry_run:
        console.print("[DRY-RUN PREVIEW]")

    if notes_text:
        if dry_run:
            bordered.create_bordered_content(
                notes_text,
                title="RELEASE NOTES PREVIEW",
                dry_run=True,
            )
        else:
            logger.info("Release notes (commit body / tag message):")
            console.print(notes_text)

    # Apply changes
    files_to_add: list[str] = []

    if getattr(args, "changelog", False):
        changelog_path_str = getattr(args, "changelog_file", None) or "CHANGELOG.md"
        changelog_path = str(changelog_path_str)
        # Prepare changelog content for preview or write
        changelog_date = datetime.date.today().isoformat()
        changelog_content = _build_changelog_content(
            cfg,
            current_version,
            tag_prefix,
            str(target_version),
            changelog_date,
            notes_text or "",
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

        # Show how the annotated tag message would look
        if do_tag and not getattr(args, "no_tag", False):
            tag_message = notes_text or tag_name
            # Append preview footer with current time and git author (best-effort)
            try:
                now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            except Exception:
                now_str = ""
            author_name = ""
            author_email = ""
            try:
                author_name = (
                    subprocess.check_output(
                        ["git", "config", "user.name"], text=True
                    )
                    .strip()
                    or ""
                )
            except Exception:
                author_name = ""
            try:
                author_email = (
                    subprocess.check_output(
                        ["git", "config", "user.email"], text=True
                    )
                    .strip()
                    or ""
                )
            except Exception:
                author_email = ""

            footer_parts: list[str] = []
            if now_str:
                footer_parts.append(f"Date: {now_str}")
            if author_name or author_email:
                if author_email:
                    footer_parts.append(f"Author: {author_name} <{author_email}>".strip())
                else:
                    footer_parts.append(f"Author: {author_name}".strip())

            if footer_parts:
                tag_message_with_footer = (
                    f"{tag_message}\n" + " - ".join(footer_parts)
                )
            else:
                tag_message_with_footer = tag_message

            bordered.create_bordered_content(
                tag_message_with_footer,
                title="TAG NOTES PREVIEW",
                dry_run=True,
            )
        else:
            logger.info(
                "Dry-run: tagging is disabled (--no-tag); no annotated tag "
                "would be created."
            )

        # Preview remote release actions, if requested
        create_gitlab_release = bool(getattr(args, "gitlab_release", False))
        create_github_draft = bool(getattr(args, "github_draft_release", False))

        if create_gitlab_release or create_github_draft:
            if getattr(args, "no_tag", False):
                logger.info(
                    "Dry-run: remote releases would be skipped because tagging "
                    "is disabled (--no-tag)."
                )
            else:
                logger.info("Dry-run: remote releases that would be created:")
                if create_gitlab_release:
                    logger.info(
                        f"- GitLab Release for tag {tag_name} "
                        "(description taken from release notes above)"
                    )
                if create_github_draft:
                    logger.info(
                        f"- GitHub draft Release for tag {tag_name} "
                        "(body taken from release notes above)"
                    )

        return 0

    # Write version to file(s) after confirming not dry-run
    updated_file = provider.write_version(
        str(target_version), use_native=cfg.project.use_native
    )
    files_to_add.append(str(updated_file))

    # Update additional files from config (e.g., pkg/__init__.py:__version__, setup.cfg:metadata.version)
    logger.debug(f"Additional file targets: {cfg.release.version_targets}")
    for entry in cfg.release.version_targets or []:
        try:
            path, selector = entry.split(":", 1)
        except ValueError:
            continue
        _update_additional_file_version(
            path.strip(), selector.strip(), str(target_version), files_to_add
        )
        logger.debug(f"Updated file target: {entry}")

    try:
        _git_commit_tag_push(
            files_to_add, tag_name, notes_text, do_commit, do_tag, do_push
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")
        raise _Exit(1)

    # Optional: create remote Releases (GitLab or GitHub draft)
    create_gitlab_release = bool(getattr(args, "gitlab_release", False))
    create_github_draft = bool(getattr(args, "github_draft_release", False))

    if create_gitlab_release or create_github_draft:
        if not do_tag:
            logger.warning(
                "Skipping remote release creation because tagging was disabled "
                "(--no-tag)."
            )
        elif not do_push:
            logger.warning(
                "Skipping remote release creation because --push was not used; "
                "use --push to push commits and tags before creating remote releases."
            )
        else:
            if create_gitlab_release:
                _create_gitlab_release(tag_name, notes_text or "")
            if create_github_draft:
                _create_github_draft_release(tag_name, notes_text or "")

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
    """Numeric selection UI for pre-release mode.

    Returns: (bump_type or 'manual' or 'continue', manual_value, do_pre, do_finalize)
    """
    parsed = parse(current_v)
    base = parsed.base()
    recommended = _recommend_bump_type()

    entries: list[Tuple[str, str, bool, bool]] = []
    # (bump_type/manual/continue/finalize/cancel, label, do_pre, do_finalize)

    if is_pre_now:
        # Current version is already a pre-release
        # 1) Continue pre-release on the same base (rc.N -> rc.N+1)
        cont_v = apply_prerelease(
            base,
            previous_version=current_v,
            channel=channel,
            auto_increment=auto_increment,
        )
        entries.append(
            (
                "continue",
                f"Continue pre-release → {tag_prefix}{cont_v}",
                True,
                False,
            )
        )

        # 2–4) Bump base (patch/minor/major) and start new pre-release sequence
        for key, label_prefix in [
            ("patch", "Patch base"),
            ("minor", "Minor base"),
            ("major", "Major base"),
        ]:
            bumped_base = bump_base(base, key)
            pre_v = apply_prerelease(
                bumped_base,
                previous_version=None,
                channel=channel,
                auto_increment=auto_increment,
            )
            entries.append(
                (
                    key,
                    f"{label_prefix} → {tag_prefix}{pre_v}",
                    True,
                    False,
                )
            )

        # 5) Finalize current pre-release to stable
        entries.append(
            (
                "finalize",
                f"Finalize current pre-release → {tag_prefix}{finalize(current_v)}",
                False,
                True,
            )
        )
    else:
        # Current version is stable: bump base first, then start pre-release
        for key, label_prefix in [
            ("patch", "Patch"),
            ("minor", "Minor"),
            ("major", "Major"),
        ]:
            bumped_base = bump_base(base, key)
            pre_v = apply_prerelease(
                bumped_base,
                previous_version=None,
                channel=channel,
                auto_increment=auto_increment,
            )
            entries.append(
                (
                    key,
                    f"{label_prefix} → {tag_prefix}{pre_v}",
                    True,
                    False,
                )
            )

    # Manual + Cancel entries (common to both cases)
    entries.append(("manual", "Manual → enter exact version", False, False))
    entries.append(("cancel", "Cancel", False, False))

    # Print list
    console.print("\n[bold]Select pre-release option[/bold]")
    for i, (key, label, _p, _f) in enumerate(entries, start=1):
        suffix = ""
        if key in {"patch", "minor", "major"} and key == recommended:
            suffix = " [recommended]"
        console.print(f"  {i}) {label}{suffix}")

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
                    manual = prompt_input("Enter version (e.g., 1.2.3-rc.1)")
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


def run(args: Any) -> int:
    """Wrapper that normalizes early exits from `_run_impl`.

    Converts internal `_Exit` exceptions to integer exit codes for the CLI.
    """
    try:
        return _run_impl(args)
    except _Exit as exc:
        return exc.code
