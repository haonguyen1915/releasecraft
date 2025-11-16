from pathlib import Path

from releaser.commit_lint import validate_commit_message


def test_valid_simple_header():
    msg = "feat: add new feature"
    violations = validate_commit_message(msg)
    assert violations == []


def test_invalid_missing_colon():
    msg = "feat add missing colon"
    violations = validate_commit_message(msg)
    assert any(v.rule == "header.format" for v in violations)


def test_allow_bang_breaking():
    msg = "fix(core)!: drop deprecated flag"
    violations = validate_commit_message(msg)
    assert violations == []


def test_subject_length_limit(tmp_path: Path, monkeypatch):
    # Enforce a small limit via config monkeypatch by editing loader to return custom
    from releaser.config import load as cfgload
    from releaser import commit_lint as cl

    cfg = cfgload.load_config()
    cfg.commit_lint.subject_max_length = 5

    # Patch the function reference used inside commit_lint module
    monkeypatch.setattr(cl, "load_config", lambda *a, **k: cfg)

    msg = "feat: subject too long here"
    violations = validate_commit_message(msg)
    assert any(v.rule == "subject.length" for v in violations)


def test_skip_merge_and_revert():
    assert validate_commit_message("Merge branch 'x'") == []
    assert validate_commit_message('Revert "some commit"') == []
