from __future__ import annotations

try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    # Light fallback to avoid hard dependency during import paths that don't use AI
    class BaseModel:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


class Section(BaseModel):
    title: str
    items: list[str]


class ReleaseNotes(BaseModel):
    summary: str | None = None
    sections: list[Section] | None = None
    highlights: list[str] | None = None
    breaking_changes: list[str] | None = None
    limitations: list[str] | None = None

    def to_markdown(self) -> str:
        parts: list[str] = []
        if self.summary:
            parts.append(self.summary.strip())
            parts.append("")
        if self.highlights:
            parts.append("### Highlights")
            parts.extend(f"- {h}" for h in self.highlights if h)
            parts.append("")
        if self.breaking_changes:
            parts.append("### Breaking Changes")
            parts.extend(f"- {b}" for b in self.breaking_changes if b)
            parts.append("")
        if self.sections:
            for sec in self.sections:
                if not sec or not sec.title or not sec.items:
                    continue
                parts.append(f"### {sec.title}")
                parts.extend(item for item in sec.items if item)
                parts.append("")
        if self.limitations:
            parts.append("### Limitations")
            parts.extend(f"- {l}" for l in self.limitations if l)
            parts.append("")
        return "\n".join(parts).strip()

