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
            parts.extend(f"- {h}" for h in (self.highlights or []))
            parts.append("")

        # Breaking changes (important for users)
        if self.breaking_changes:
            parts.append("### Breaking Changes")
            parts.extend(f"- {b}" for b in (self.breaking_changes or []))
            parts.append("")

        return "\n".join(parts).strip()


class CommitMessage(BaseModel):
    type: str
    scope: str | None = None
    subject: str
    body: str | None = None
    breaking_change: bool = False
    footers: dict[str, str] | None = None

    def to_text(self) -> str:
        scope_part = f"({self.scope})" if self.scope else ""
        bang = "!" if self.breaking_change else ""
        header = f"{self.type}{scope_part}{bang}: {self.subject}"
        lines: list[str] = [header]
        if self.body:
            lines.append("")
            lines.append(self.body.strip())
        if self.breaking_change:
            lines.append("")
            lines.append("BREAKING CHANGE: See details above.")
        if self.footers:
            lines.append("")
            for k, v in self.footers.items():
                lines.append(f"{k}: {v}")
        return "\n".join(lines).strip()
