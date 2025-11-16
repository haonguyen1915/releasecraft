from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<pre>[0-9A-Za-z\.-]+))?(?:\+(?P<meta>[0-9A-Za-z\.-]+))?$"
)


@dataclass
class ParsedVersion:
    major: int
    minor: int
    patch: int
    pre: Optional[str] = None
    meta: Optional[str] = None

    def base(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def as_string(self) -> str:
        s = self.base()
        if self.pre:
            s += f"-{self.pre}"
        if self.meta:
            s += f"+{self.meta}"
        return s


def parse(version: str) -> ParsedVersion:
    m = _SEMVER_RE.match(version.strip())
    if not m:
        # Best effort: fallback to 0.0.0
        return ParsedVersion(0, 0, 0, None, None)
    return ParsedVersion(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        pre=m.group("pre"),
        meta=m.group("meta"),
    )


def bump_base(current: str, bump_type: str) -> str:
    v = parse(current)
    if bump_type == "major":
        return f"{v.major + 1}.0.0"
    if bump_type == "minor":
        return f"{v.major}.{v.minor + 1}.0"
    # default patch
    return f"{v.major}.{v.minor}.{v.patch + 1}"


def finalize(version: str) -> str:
    v = parse(version)
    v.pre = None
    v.meta = None
    return v.as_string()


def apply_prerelease(
    base_version: str,
    previous_version: Optional[str],
    channel: str,
    auto_increment: bool = True,
) -> str:
    """Return a pre-release version for the given base.

    If previous_version matches the same base and channel (e.g., 1.2.3-rc.2),
    increment the numeric suffix when auto_increment is True; otherwise start at 1.
    """
    # Determine next number
    next_n = 1

    if previous_version:
        prev = parse(previous_version)
        if prev.base() == base_version and prev.pre:
            # Try to match channel.N
            m = re.match(rf"^{re.escape(channel)}\.(\d+)$", prev.pre)
            if m:
                n = int(m.group(1))
                next_n = n + 1 if auto_increment else n

    return f"{base_version}-{channel}.{next_n}"
