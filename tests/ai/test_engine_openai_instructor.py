from pathlib import Path
from types import SimpleNamespace
import tempfile

import pytest

from releaser.ai.engine import openai_instructor as eng
from releaser.ai.schemas import ReleaseNotes


class FakeInst:
    def __init__(self):
        class Chat:
            class Completions:
                @staticmethod
                def create(**kwargs):
                    # Simulate Instructor returning a ReleaseNotes instance
                    return ReleaseNotes(
                        summary="Summary text",
                        highlights=["One"],
                        breaking_changes=[],
                    )

            completions = Completions()

        self.chat = Chat()


class FakeInstructorModule:
    @staticmethod
    def from_openai(client):
        return FakeInst()


class FakeOpenAI:
    def __init__(self, api_key=None):
        self.api_key = api_key


class FakeJinja2:
    """Fake Jinja2 module for testing."""
    class Template:
        def __init__(self, template_str):
            self.template_str = template_str

        def render(self, **context):
            # Simple string substitution for testing
            result = self.template_str
            for key, value in context.items():
                if isinstance(value, list):
                    # For commits list
                    if value and isinstance(value[0], dict):
                        commits_text = "\n".join([
                            f"- {c.get('hash', '')[:8]}: {c.get('message', '')}"
                            for c in value
                        ])
                        result = result.replace(f"{{{{ {key}|length }}}}", str(len(value)))
                        result = result.replace(f"{{{{ {key} }}}}", commits_text)
                elif isinstance(value, dict):
                    # For diffs dict
                    result = result.replace(f"{{{{ {key} }}}}", str(value))
                else:
                    # For simple values
                    result = result.replace(f"{{{{ {key} }}}}", str(value))
            return result


def test_generate_structured(monkeypatch):
    """Test the generic generate_structured function."""
    # Monkeypatch importer to return fake modules
    monkeypatch.setattr(eng, "_import_clients", lambda: (FakeInstructorModule, FakeOpenAI))

    rn = eng.generate_structured(
        api_key="test-key",
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=256,
        system_prompt="You are a helpful assistant",
        user_prompt="Generate release notes",
        response_model=ReleaseNotes,
    )
    assert isinstance(rn, ReleaseNotes)
    assert rn.summary == "Summary text"
    assert rn.highlights == ["One"]


def test_load_template_from_default(tmp_path, monkeypatch):
    """Test loading template from default prompts directory."""
    # Create a mock prompts directory
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    template_content = "This is a test template"
    template_file = prompts_dir / "test_template.md"
    template_file.write_text(template_content)

    # Monkeypatch the __file__ path to point to our tmp directory
    original_file = Path(eng.__file__)
    fake_file = tmp_path / "engine" / "openai_instructor.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(eng, "__file__", str(fake_file))

    # Test loading default template
    result = eng._load_template(custom_path=None, default_filename="test_template.md")
    assert result == template_content


def test_load_template_from_custom_path(tmp_path):
    """Test loading template from custom path."""
    custom_template = tmp_path / "custom_template.md"
    custom_content = "Custom template content"
    custom_template.write_text(custom_content)

    result = eng._load_template(
        custom_path=str(custom_template),
        default_filename="ignored.md"
    )
    assert result == custom_content


def test_load_template_custom_not_found():
    """Test that loading non-existent custom template raises error."""
    with pytest.raises(FileNotFoundError, match="Custom template not found"):
        eng._load_template(
            custom_path="/nonexistent/path/template.md",
            default_filename="ignored.md"
        )


def test_render_template(monkeypatch):
    """Test Jinja2 template rendering."""
    monkeypatch.setattr(eng, "_import_jinja2", lambda: FakeJinja2)

    template_str = "Version {{ version }}, Count: {{ count }}"
    result = eng._render_template(template_str, version="1.2.0", count=5)

    assert "1.2.0" in result
    assert "5" in result


def test_generate_release_notes_success(monkeypatch, tmp_path):
    """Test successful generation of release notes with all components."""
    # Setup fake modules
    monkeypatch.setattr(eng, "_import_clients", lambda: (FakeInstructorModule, FakeOpenAI))
    monkeypatch.setattr(eng, "_import_jinja2", lambda: FakeJinja2)

    # Create temporary template files
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    system_template = "You are an AI assistant for version {{ current_version }}"
    system_file = prompts_dir / "system_release_notes.md"
    system_file.write_text(system_template)

    user_template = (
        "Generate notes for {{ current_version }} from {{ previous_version }}.\n"
        "Commits ({{ commits|length }} total):\n"
        "{{ commits }}\n"
        "Diffs: {{ diffs }}"
    )
    user_file = prompts_dir / "release_notes.md.j2"
    user_file.write_text(user_template)

    # Monkeypatch the __file__ path
    fake_file = tmp_path / "engine" / "openai_instructor.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(eng, "__file__", str(fake_file))

    # Test data
    commits = [
        {
            "hash": "abc123def456",
            "message": "feat: add new feature",
            "author": "Jane Doe <jane@example.com>",
            "date": "2024-01-15"
        },
        {
            "hash": "def456abc123",
            "message": "fix: resolve bug",
            "author": "John Smith <john@example.com>",
            "date": "2024-01-14"
        }
    ]

    diffs = {
        "abc123def456": "diff --git a/file.py b/file.py\n+new line"
    }

    # Call the function
    notes = eng.generate_release_notes(
        api_key="test-key",
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=800,
        commits=commits,
        current_version="1.2.0",
        previous_version="1.1.0",
        diffs=diffs,
    )

    # Assertions
    assert isinstance(notes, ReleaseNotes)
    assert notes.summary == "Summary text"
    assert notes.highlights == ["One"]

    # Test markdown generation
    md = notes.to_markdown()
    assert "Summary text" in md


def test_generate_release_notes_missing_api_key(monkeypatch, tmp_path):
    """Test that missing API key raises ValueError."""
    # Setup templates
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    system_file = prompts_dir / "system_release_notes.md"
    system_file.write_text("System prompt")

    user_file = prompts_dir / "release_notes.md.j2"
    user_file.write_text("User prompt")

    fake_file = tmp_path / "engine" / "openai_instructor.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(eng, "__file__", str(fake_file))

    with pytest.raises(ValueError, match="API key is required"):
        eng.generate_release_notes(
            api_key=None,
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=800,
            commits=[],
            current_version="1.2.0",
            previous_version="1.1.0",
        )


def test_generate_release_notes_with_custom_templates(monkeypatch, tmp_path):
    """Test using custom template files."""
    monkeypatch.setattr(eng, "_import_clients", lambda: (FakeInstructorModule, FakeOpenAI))
    monkeypatch.setattr(eng, "_import_jinja2", lambda: FakeJinja2)

    # Create custom templates
    custom_system = tmp_path / "my_system.md"
    custom_system.write_text("Custom system prompt for {{ current_version }}")

    custom_user = tmp_path / "my_user.md.j2"
    custom_user.write_text("Custom user prompt: {{ commits|length }} commits")

    commits = [{"hash": "abc123", "message": "test", "author": "Test", "date": "2024-01-01"}]

    notes = eng.generate_release_notes(
        api_key="test-key",
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=800,
        commits=commits,
        current_version="2.0.0",
        previous_version="1.9.0",
        system_prompt_file=str(custom_system),
        user_prompt_file=str(custom_user),
    )

    assert isinstance(notes, ReleaseNotes)


def test_generate_release_notes_without_diffs(monkeypatch, tmp_path):
    """Test generation without providing diffs (diffs=None)."""
    monkeypatch.setattr(eng, "_import_clients", lambda: (FakeInstructorModule, FakeOpenAI))
    monkeypatch.setattr(eng, "_import_jinja2", lambda: FakeJinja2)

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    system_file = prompts_dir / "system_release_notes.md"
    system_file.write_text("System")

    user_file = prompts_dir / "release_notes.md.j2"
    user_file.write_text("User: {{ commits|length }} commits, diffs={{ diffs }}")

    fake_file = tmp_path / "engine" / "openai_instructor.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(eng, "__file__", str(fake_file))

    commits = [{"hash": "abc", "message": "test", "author": "Test", "date": "2024-01-01"}]

    notes = eng.generate_release_notes(
        api_key="test-key",
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=800,
        commits=commits,
        current_version="1.0.0",
        previous_version="0.9.0",
        # diffs is None (default)
    )

    assert isinstance(notes, ReleaseNotes)

