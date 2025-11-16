import os

import pytest

from releaser.ai.engine.openai_instructor import generate_commit_message
from releaser.ai.schemas import CommitMessage


def test_generate_commit_message_heuristic_docs():
    cm = generate_commit_message(
        api_key=None,  # force heuristic path
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=400,
        files=["docs/README.md", "CHANGELOG.md"],
        diffs={
            "docs/README.md": "+ Add usage instructions\n+ Update badges",
            "CHANGELOG.md": "+ 1.2.0 notes",
        },
    )
    assert isinstance(cm, CommitMessage)
    assert cm.type == "docs"
    assert cm.subject.lower().startswith("update")


def test_generate_commit_message_heuristic_fix():
    cm = generate_commit_message(
        api_key=None,
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=400,
        files=["releaser/ai/engine/openai_instructor.py"],
        diffs={
            "releaser/ai/engine/openai_instructor.py": "+ fix error handling and exception messages",
        },
    )
    assert cm.type == "fix"

