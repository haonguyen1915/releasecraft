"""Integration tests for AI engine with real OpenAI API.

These tests use actual API calls and will be skipped if OPENAI_API_KEY is not set.
Run with: pytest tests/ai/test_engine_integration.py -v -s
"""

import os

import pytest

from releaser.ai.engine.openai_instructor import generate_release_notes
from releaser.ai.schemas import ReleaseNotes


# Skip all tests in this module if API key is not available
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping integration tests",
)


@pytest.fixture
def sample_commits():
    """Sample commits for testing."""
    return [
        {
            "hash": "abc123def456789",
            "message": "feat: add AI-powered release notes generation",
            "author": "Jane Doe <jane@example.com>",
            "date": "2024-01-15",
        },
        {
            "hash": "def456abc123456",
            "message": "fix!: resolve critical security vulnerability in authentication",
            "author": "John Smith <john@example.com>",
            "date": "2024-01-14",
        },
        {
            "hash": "789abc456def123",
            "message": "feat: implement template-based prompt system with Jinja2",
            "author": "Alice Johnson <alice@example.com>",
            "date": "2024-01-13",
        },
        {
            "hash": "456def789abc012",
            "message": "docs: update README with AI configuration examples",
            "author": "Bob Wilson <bob@example.com>",
            "date": "2024-01-12",
        },
        {
            "hash": "012abc345def678",
            "message": "refactor: improve error handling in template loader",
            "author": "Charlie Brown <charlie@example.com>",
            "date": "2024-01-11",
        },
    ]


@pytest.fixture
def sample_diffs():
    """Sample diffs for important commits."""
    return {
        "def456abc123456": """diff --git a/releaser/auth.py b/releaser/auth.py
index 1234567..abcdefg 100644
--- a/releaser/auth.py
+++ b/releaser/auth.py
@@ -10,7 +10,7 @@ def validate_token(token):
-    if token == "":
+    if not token or len(token) < 32:
         raise ValueError("Invalid token")

-    return hashlib.md5(token.encode()).hexdigest()
+    return hashlib.sha256(token.encode()).hexdigest()
""",
        "abc123def456789": """diff --git a/releaser/ai/engine/openai_instructor.py b/releaser/ai/engine/openai_instructor.py
index abcdefg..1234567 100644
--- a/releaser/ai/engine/openai_instructor.py
+++ b/releaser/ai/engine/openai_instructor.py
@@ -177,0 +178,100 @@ def _render_template(template_str: str, **context: Any) -> str:
+def generate_release_notes(
+    *,
+    api_key: str | None,
+    model: str,
+    temperature: float,
+    max_tokens: int,
+    commits: list[dict[str, Any]],
+    current_version: str,
+    previous_version: str,
+    diffs: dict[str, str] | None = None,
+    system_prompt_file: str | None = None,
+    user_prompt_file: str | None = None,
+) -> ReleaseNotes:
""",
    }


def test_generate_release_notes_real_api(sample_commits):
    """Test release notes generation with real OpenAI API (no diffs)."""
    api_key = os.getenv("OPENAI_API_KEY")

    print("\n" + "=" * 80)
    print("Testing with real OpenAI API (commits only)")
    print("=" * 80)

    notes = generate_release_notes(
        api_key=api_key,
        model="gpt-4o-mini",  # Fast and cost-effective
        temperature=0.2,
        max_tokens=1000,
        commits=sample_commits,
        current_version="1.2.0",
        previous_version="1.1.0",
    )

    # Assertions
    assert isinstance(notes, ReleaseNotes)
    assert notes.summary is not None, "Summary should be generated"

    print(f"\n📝 Summary: {notes.summary}")

    if notes.highlights:
        print(f"\n✨ Highlights ({len(notes.highlights)}):")
        for highlight in notes.highlights:
            print(f"  - {highlight}")

    if notes.breaking_changes:
        print(f"\n⚠️  Breaking Changes ({len(notes.breaking_changes)}):")
        for change in notes.breaking_changes:
            print(f"  - {change}")

    if notes.sections:
        print(f"\n📚 Sections ({len(notes.sections)}):")
        for section in notes.sections:
            print(f"  {section.title} ({len(section.items)} items)")

    if notes.limitations:
        print(f"\n⚡ Limitations ({len(notes.limitations)}):")
        for limitation in notes.limitations:
            print(f"  - {limitation}")

    # Generate markdown
    markdown = notes.to_markdown()
    assert len(markdown) > 0, "Markdown output should not be empty"

    print("\n" + "=" * 80)
    print("Generated Markdown:")
    print("=" * 80)
    print(markdown)
    print("=" * 80)

    # Verify structure
    assert (
        notes.breaking_changes is not None
    ), "Should identify breaking changes from fix! commit"
    if notes.breaking_changes:
        assert (
            len(notes.breaking_changes) > 0
        ), "Should have at least one breaking change"


def test_generate_release_notes_with_diffs(sample_commits, sample_diffs):
    """Test release notes generation with real OpenAI API (with diffs)."""
    api_key = os.getenv("OPENAI_API_KEY")

    print("\n" + "=" * 80)
    print("Testing with real OpenAI API (commits + diffs)")
    print("=" * 80)

    notes = generate_release_notes(
        api_key=api_key,
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=1500,  # More tokens for diffs
        commits=sample_commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        diffs=sample_diffs,
    )

    # Assertions
    assert isinstance(notes, ReleaseNotes)
    assert notes.summary is not None

    print(f"\n📝 Summary: {notes.summary}")

    if notes.highlights:
        print(f"\n✨ Highlights ({len(notes.highlights)}):")
        for highlight in notes.highlights:
            print(f"  - {highlight}")

    if notes.breaking_changes:
        print(f"\n⚠️  Breaking Changes ({len(notes.breaking_changes)}):")
        for change in notes.breaking_changes:
            print(f"  - {change}")

    if notes.sections:
        print(f"\n📚 Sections ({len(notes.sections)}):")
        for section in notes.sections:
            print(f"  {section.title} ({len(section.items)} items)")

    # Generate markdown
    markdown = notes.to_markdown()

    print("\n" + "=" * 80)
    print("Generated Markdown (with diffs):")
    print("=" * 80)
    print(markdown)
    print("=" * 80)

    # Verify breaking changes were identified
    assert notes.breaking_changes is not None
    if notes.breaking_changes:
        # Should mention security or authentication since we have a security fix
        breaking_text = " ".join(notes.breaking_changes).lower()
        assert any(
            word in breaking_text
            for word in ["security", "authentication", "token", "hash"]
        ), "Breaking changes should mention security-related changes"


def test_generate_release_notes_custom_model(sample_commits):
    """Test with a different model (if available)."""
    api_key = os.getenv("OPENAI_API_KEY")

    # Test with gpt-4o-mini (faster/cheaper for testing)
    notes = generate_release_notes(
        api_key=api_key,
        model="gpt-4o-mini",
        temperature=0.1,  # Very deterministic
        max_tokens=800,
        commits=sample_commits[:3],  # Fewer commits
        current_version="1.1.0",
        previous_version="1.0.0",
    )

    assert isinstance(notes, ReleaseNotes)
    assert notes.summary is not None

    print("\n" + "=" * 80)
    print("Model: gpt-4o-mini, Temperature: 0.1")
    print("=" * 80)
    print(notes.to_markdown())
    print("=" * 80)


def test_generate_release_notes_high_temperature(sample_commits):
    """Test with higher temperature for more creative output."""
    api_key = os.getenv("OPENAI_API_KEY")

    notes = generate_release_notes(
        api_key=api_key,
        model="gpt-4o-mini",
        temperature=0.7,  # More creative
        max_tokens=1000,
        commits=sample_commits,
        current_version="2.0.0",
        previous_version="1.9.0",
    )

    assert isinstance(notes, ReleaseNotes)
    assert notes.summary is not None

    print("\n" + "=" * 80)
    print("Model: gpt-4o-mini, Temperature: 0.7 (creative)")
    print("=" * 80)
    print(notes.to_markdown())
    print("=" * 80)


@pytest.mark.parametrize("max_tokens", [500, 1000, 1500])
def test_generate_release_notes_token_limits(sample_commits, max_tokens):
    """Test with different token limits."""
    api_key = os.getenv("OPENAI_API_KEY")

    notes = generate_release_notes(
        api_key=api_key,
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=max_tokens,
        commits=sample_commits,
        current_version="1.2.0",
        previous_version="1.1.0",
    )

    assert isinstance(notes, ReleaseNotes)

    print(f"\n{'='*80}")
    print(f"Max Tokens: {max_tokens}")
    print(f"{'='*80}")
    markdown = notes.to_markdown()
    print(f"Output length: {len(markdown)} characters")
    print(f"{'='*80}")
