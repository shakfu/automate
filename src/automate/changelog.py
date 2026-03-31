"""Keep a Changelog parser.

Parses markdown files following the Keep a Changelog format:
https://keepachangelog.com/en/1.0.0/
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# ## [0.2.0] - 2025-06-01  or  ## [Unreleased]
VERSION_RE = re.compile(
    r"^## \[(?P<version>.+?)\](?:\s*-\s*(?P<date>\d{4}-\d{2}-\d{2}))?\s*$"
)

# ### Added, ### Fixed, etc.
SECTION_RE = re.compile(r"^### (?P<name>\w+)\s*$")

VALID_SECTIONS = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}


@dataclass
class ChangelogEntry:
    """A single version entry in a Keep a Changelog file."""

    version: str
    release_date: date | None = None
    sections: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_unreleased(self) -> bool:
        return self.version.lower() == "unreleased"

    def to_markdown(self) -> str:
        """Render this entry's content as markdown (without the version header)."""
        parts: list[str] = []
        for section_name, items in self.sections.items():
            parts.append(f"### {section_name}\n")
            for item in items:
                parts.append(f"- {item}")
            parts.append("")
        return "\n".join(parts).rstrip("\n")


@dataclass
class Changelog:
    """Parsed Keep a Changelog file."""

    title: str
    preamble: str
    entries: list[ChangelogEntry] = field(default_factory=list)

    def get_version(self, version: str) -> ChangelogEntry | None:
        """Look up an entry by version string (e.g. '0.2.0')."""
        for entry in self.entries:
            if entry.version == version:
                return entry
        return None

    def get_unreleased(self) -> ChangelogEntry | None:
        """Return the [Unreleased] entry, if any."""
        for entry in self.entries:
            if entry.is_unreleased:
                return entry
        return None

    @property
    def versions(self) -> list[str]:
        """List all version strings in order."""
        return [e.version for e in self.entries]


def parse_changelog(path: Path) -> Changelog:
    """Parse a Keep a Changelog formatted markdown file.

    Args:
        path: Path to the CHANGELOG.md file.

    Returns:
        Parsed Changelog object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file has no title heading.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = ""
    preamble_lines: list[str] = []
    entries: list[ChangelogEntry] = []
    current_entry: ChangelogEntry | None = None
    current_section: str | None = None
    in_preamble = True

    for line in lines:
        # Title: first H1
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue

        # Version header
        m = VERSION_RE.match(line)
        if m:
            in_preamble = False
            release_date = None
            if m.group("date"):
                release_date = date.fromisoformat(m.group("date"))
            current_entry = ChangelogEntry(
                version=m.group("version"),
                release_date=release_date,
            )
            entries.append(current_entry)
            current_section = None
            continue

        # Section header (### Added, etc.)
        m = SECTION_RE.match(line)
        if m and current_entry is not None:
            current_section = m.group("name")
            if current_section not in current_entry.sections:
                current_entry.sections[current_section] = []
            continue

        # List item
        if (
            line.startswith("- ")
            and current_entry is not None
            and current_section is not None
        ):
            current_entry.sections[current_section].append(line[2:])
            continue

        # Continuation line (indented, part of previous list item)
        if (
            line.startswith("  ")
            and current_entry is not None
            and current_section is not None
            and current_section in current_entry.sections
            and current_entry.sections[current_section]
        ):
            prev = current_entry.sections[current_section][-1]
            current_entry.sections[current_section][-1] = prev + "\n" + line
            continue

        # Preamble text (between title and first version)
        if in_preamble and title:
            preamble_lines.append(line)

    if not title:
        raise ValueError(f"No title heading found in {path}")

    preamble = "\n".join(preamble_lines).strip()

    return Changelog(title=title, preamble=preamble, entries=entries)
