from __future__ import annotations

from pydantic import BaseModel


class ReleaseNotes(BaseModel):
    """Simplified release notes focused on highlights.

    Since conventional commits already categorize changes (feat:, fix:, etc.),
    we focus on high-level highlights rather than detailed sections.
    """
    summary: str | None = None
    highlights: list[str] | None = None
    breaking_changes: list[str] | None = None

    def to_markdown(self) -> str:
        """Convert release notes to markdown format.

        Returns:
            Markdown string with summary, highlights, and breaking changes.
        """
        parts: list[str] = []

        # Summary
        if self.summary:
            parts.append(self.summary.strip())
            parts.append("")

        # Highlights (main focus)
        if self.highlights:
            parts.append("### Highlights")
            parts.extend(f"- {h}" for h in self.highlights if h)
            parts.append("")

        # Breaking changes (important for users)
        if self.breaking_changes:
            parts.append("### Breaking Changes")
            parts.extend(f"- {b}" for b in self.breaking_changes if b)
            parts.append("")

        return "\n".join(parts).strip()
