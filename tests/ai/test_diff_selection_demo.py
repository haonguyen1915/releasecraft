"""Demo showing when diffs ARE included vs when they're NOT."""

from releaser.ai.data_collector import identify_important_commits


def test_clear_commits_no_diffs_needed():
    """Clear commit messages don't need diffs."""
    commits = [
        {"hash": "abc1", "message": "feat: add OAuth2 authentication with JWT tokens", "author": "Dev", "date": "2024-01-01"},
        {"hash": "abc2", "message": "fix: resolve memory leak in cache manager", "author": "Dev", "date": "2024-01-01"},
        {"hash": "abc3", "message": "docs: update API documentation with examples", "author": "Dev", "date": "2024-01-01"},
    ]

    important = identify_important_commits(commits)

    print("\n✅ CLEAR COMMITS (no diffs needed):")
    for commit in commits:
        is_important = commit["hash"] in [c["hash"] for c in important]
        status = "❌ NO DIFF" if not is_important else "✓ DIFF"
        print(f"  {status}: {commit['message']}")

    assert len(important) == 0, "Clear commits shouldn't need diffs"


def test_unclear_commits_need_diffs():
    """Unclear/vague commits DO need diffs for context."""
    commits = [
        {"hash": "abc1", "message": "update dependencies", "author": "Dev", "date": "2024-01-01"},  # No prefix
        {"hash": "abc2", "message": "feat: update", "author": "Dev", "date": "2024-01-01"},  # Vague
        {"hash": "abc3", "message": "fix: changes", "author": "Dev", "date": "2024-01-01"},  # Vague
        {"hash": "abc4", "message": "stuff", "author": "Dev", "date": "2024-01-01"},  # No prefix, vague
    ]

    important = identify_important_commits(commits)

    print("\n⚠️  UNCLEAR COMMITS (diffs needed):")
    for commit in commits:
        is_important = commit["hash"] in [c["hash"] for c in important]
        status = "✓ DIFF" if is_important else "❌ NO DIFF"
        print(f"  {status}: {commit['message']}")

    assert len(important) == 4, "All unclear commits should need diffs"


def test_breaking_changes_always_need_diffs():
    """Breaking changes ALWAYS get diffs."""
    commits = [
        {"hash": "abc1", "message": "feat!: change API response format", "author": "Dev", "date": "2024-01-01"},
        {"hash": "abc2", "message": "fix(auth)!: update token validation", "author": "Dev", "date": "2024-01-01"},
        {"hash": "abc3", "message": "refactor: BREAKING CHANGE: remove deprecated methods", "author": "Dev", "date": "2024-01-01"},
    ]

    important = identify_important_commits(commits)

    print("\n🚨 BREAKING CHANGES (always need diffs):")
    for commit in commits:
        is_important = commit["hash"] in [c["hash"] for c in important]
        status = "✓ DIFF" if is_important else "❌ NO DIFF"
        print(f"  {status}: {commit['message']}")

    assert len(important) == 3, "All breaking changes should get diffs"


def test_security_commits_always_need_diffs():
    """Security-related commits ALWAYS get diffs."""
    commits = [
        {"hash": "abc1", "message": "fix: resolve security vulnerability in auth", "author": "Dev", "date": "2024-01-01"},
        {"hash": "abc2", "message": "patch CVE-2024-1234", "author": "Dev", "date": "2024-01-01"},
        {"hash": "abc3", "message": "fix: prevent XSS attack vector", "author": "Dev", "date": "2024-01-01"},
        {"hash": "abc4", "message": "feat: add SQL injection protection", "author": "Dev", "date": "2024-01-01"},
    ]

    important = identify_important_commits(commits)

    print("\n🔒 SECURITY COMMITS (always need diffs):")
    for commit in commits:
        is_important = commit["hash"] in [c["hash"] for c in important]
        status = "✓ DIFF" if is_important else "❌ NO DIFF"
        print(f"  {status}: {commit['message']}")

    assert len(important) == 4, "All security commits should get diffs"


def test_mixed_scenario():
    """Real-world mix of commits."""
    commits = [
        {"hash": "abc1", "message": "feat: add comprehensive OAuth2 authentication", "author": "Dev", "date": "2024-01-01"},  # Clear, no diff
        {"hash": "abc2", "message": "fix!: critical authentication bug", "author": "Dev", "date": "2024-01-01"},  # Breaking, needs diff
        {"hash": "abc3", "message": "update readme", "author": "Dev", "date": "2024-01-01"},  # No prefix, needs diff
        {"hash": "abc4", "message": "docs: improve API documentation", "author": "Dev", "date": "2024-01-01"},  # Clear, no diff
        {"hash": "abc5", "message": "fix: resolve security issue in token handling", "author": "Dev", "date": "2024-01-01"},  # Security, needs diff
        {"hash": "abc6", "message": "feat: changes", "author": "Dev", "date": "2024-01-01"},  # Vague, needs diff
    ]

    important = identify_important_commits(commits)

    print("\n📊 MIXED SCENARIO:")
    for commit in commits:
        is_important = commit["hash"] in [c["hash"] for c in important]
        status = "✓ DIFF" if is_important else "❌ NO DIFF"

        reason = ""
        if "!" in commit["message"].split(":")[0]:
            reason = "(breaking)"
        elif "security" in commit["message"].lower():
            reason = "(security)"
        elif not any(commit["message"].startswith(f"{p}:") for p in ["feat", "fix", "docs", "chore"]):
            reason = "(no prefix)"
        elif any(word in commit["message"].lower() for word in ["update", "change", "changes"]) and len(commit["message"].split(":")[-1].strip().split()) <= 2:
            reason = "(vague)"

        print(f"  {status}: {commit['message']} {reason}")

    print(f"\n  Total: {len(important)}/6 commits need diffs")
    assert len(important) == 4  # abc2, abc3, abc5, abc6