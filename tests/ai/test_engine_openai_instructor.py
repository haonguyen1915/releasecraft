from types import SimpleNamespace

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
                        sections=[],
                        highlights=["One"],
                        breaking_changes=[],
                        limitations=[],
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


def test_openai_instructor_generate_release_notes(monkeypatch):
    # Monkeypatch importer to return fake modules
    monkeypatch.setattr(eng, "_import_clients", lambda: (FakeInstructorModule, FakeOpenAI))

    rn = eng.generate_release_notes(
        api_key=None,
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=256,
        system_prompt="sys",
        user_prompt="user",
    )
    assert isinstance(rn, ReleaseNotes)
    md = rn.to_markdown()
    assert "Summary text" in md

