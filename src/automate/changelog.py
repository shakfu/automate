"""Keep a Changelog parser.

Parses markdown files following the Keep a Changelog format:
https://keepachangelog.com/en/1.0.0/

Two views of each entry are available. `ChangelogEntry.raw` is the
verbatim source text of the entry, which is what release tooling should
publish: it preserves tables, fenced code, arbitrary section headings,
and bullet styles the tokenizer does not model. `ChangelogEntry.sections`
is the structured view, useful for listing and validation but lossy,
since it keeps only recognised `### Section` blocks and `- ` bullets.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Version headings, in the shapes Keep a Changelog sanctions:
#   ## [Unreleased]
#   ## [0.2.0] - 2025-06-01
#   ## [0.2.0](https://github.com/o/r/releases/tag/v0.2.0) - 2025-06-01
#   ## [0.2.0] - 2025-06-01 [YANKED]
# The version group is [^\]]+ rather than .+? so it cannot backtrack across
# the closing bracket and swallow the date and YANKED marker into itself.
VERSION_RE = re.compile(
    r"^## \[(?P<version>[^\]]+)\]"
    r"(?:\((?P<link>[^)]*)\))?"
    r"(?:\s*-\s*(?P<date>\d{4}-\d{2}-\d{2}))?"
    r"(?:\s+\[(?P<yanked>YANKED)\])?"
    r"\s*$"
)

# Any other level-2 heading. Keep a Changelog uses `##` only for versions, so
# one that is not a version heading ends the preceding entry rather than
# silently extending it.
H2_RE = re.compile(r"^## ")

# A fenced code block, per CommonMark: three or more backticks or tildes,
# indented at most three spaces.
FENCE_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")

# Bullets Keep a Changelog does not use but authors write anyway.
OTHER_BULLET_RE = re.compile(r"^\s*[*+] \S")

# ### Added, ### Fixed, etc.
SECTION_RE = re.compile(r"^### (?P<name>\w+)\s*$")

# [0.2.0]: https://github.com/owner/repo/releases/tag/v0.2.0
LINK_REF_RE = re.compile(r"^\[[^\]]+\]:\s*\S")

# The [Unreleased]: definition in the footer, which points at a compare URL
# ending in HEAD and so needs rewriting whenever a release is cut.
UNRELEASED_LINK_REF_RE = re.compile(r"^\[Unreleased\]:\s*\S", re.IGNORECASE)

VALID_SECTIONS = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}


@dataclass
class ChangelogEntry:
    """A single version entry in a Keep a Changelog file.

    Attributes:
        version: The version string as written, e.g. "0.2.0" or "Unreleased".
        release_date: Parsed release date, or None if the heading carried none.
        yanked: True when the heading carried a trailing `[YANKED]` marker.
        link: Inline link target from the heading, if it used the
            `## [0.2.0](url)` form; None otherwise.
        sections: Structured, lossy view keyed by `### Section` name.
        raw: Verbatim entry body, excluding the version heading. Empty for
            entries parsed from a heading with no content beneath it, and for
            entries constructed directly rather than parsed.
        start_line: 1-indexed line of the version heading in the source file.
        end_line: 1-indexed last line of `raw` in the source file. Equals
            `start_line` when the entry has no body.
    """

    version: str
    release_date: date | None = None
    yanked: bool = False
    link: str | None = None
    sections: dict[str, list[str]] = field(default_factory=dict)
    raw: str = ""
    start_line: int = 0
    end_line: int = 0

    @property
    def is_unreleased(self) -> bool:
        return self.version.lower() == "unreleased"

    def to_markdown(self) -> str:
        """Re-render the parsed sections as markdown (without the version header).

        Lossy: only recognised sections and `- ` bullets survive. Prefer `raw`
        when the goal is to reproduce what the author wrote.
        """
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
    unparsed_headings: list[tuple[int, str]] = field(default_factory=list)
    """Level-2 headings after the first version that VERSION_RE could not read,
    as (line number, text). Non-empty means content was excluded from every
    entry: worth failing a release on."""

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


def _scan(lines: list[str]) -> list[tuple[int, str, bool]]:
    """Pair each line with whether it sits inside a fenced code block.

    Markdown inside a fence is content, not structure: a `# ` comment in a
    shell example is not the document title, and a `## [1.0.0]` line in an
    example changelog is not a version heading. Both the parser and the
    linter walk lines through here so they agree on what counts.
    """
    out: list[tuple[int, str, bool]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if m is None:
            out.append((index, line, fence is not None))
            continue
        marker = m.group("marker")
        if fence is None:
            # An opening backtick fence may not carry backticks in its info
            # string; a tilde fence may carry anything.
            if marker[0] == "`" and "`" in m.group("info"):
                out.append((index, line, False))
                continue
            fence = marker
            out.append((index, line, True))
        elif marker[0] == fence[0] and len(marker) >= len(fence) and not m.group("info").strip():
            out.append((index, line, True))
            fence = None
        else:
            out.append((index, line, True))
    return out


def _body_span(lines: list[str], start: int, end: int) -> tuple[int, int]:
    """Narrow the half-open range [start, end) to an entry's real body.

    Trims blank lines at both edges, then drops any trailing block of
    link-reference definitions -- the `[1.0.0]: https://...` footer that the
    Keep a Changelog template puts at the end of the file, which belongs to
    the document rather than to its last entry. Definitions that appear
    mid-entry are left alone, since something non-blank follows them.
    """
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    while end > start and LINK_REF_RE.match(lines[end - 1]):
        end -= 1
        while end > start and not lines[end - 1].strip():
            end -= 1
    return start, end


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
    heading_indices: list[int] = []
    terminators: list[int] = []
    unparsed_headings: list[tuple[int, str]] = []
    current_entry: ChangelogEntry | None = None
    current_section: str | None = None
    in_preamble = True

    for index, line, in_fence in _scan(lines):
        if in_fence:
            # Content, never structure. Still eligible as preamble text and as
            # a continuation of the list item above it.
            if (
                line.startswith("  ")
                and current_entry is not None
                and current_section is not None
                and current_entry.sections.get(current_section)
            ):
                prev = current_entry.sections[current_section][-1]
                current_entry.sections[current_section][-1] = prev + "\n" + line
            elif in_preamble and title:
                preamble_lines.append(line)
            continue

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
                yanked=m.group("yanked") is not None,
                link=m.group("link"),
                start_line=index + 1,
                end_line=index + 1,
            )
            entries.append(current_entry)
            heading_indices.append(index)
            current_section = None
            continue

        # A level-2 heading that is not a version heading. Without this, the
        # entry above it stays "current" and absorbs everything below as if it
        # were its own -- the wrong version's content, published silently.
        # Before the first version heading such a heading is just preamble
        # (Keep a Changelog templates often carry a "Types of Changes"
        # section), so it falls through to the preamble branch below.
        if H2_RE.match(line) and current_entry is not None:
            unparsed_headings.append((index + 1, line.rstrip()))
            terminators.append(index)
            current_entry = None
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
        if line.startswith("- ") and current_entry is not None and current_section is not None:
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

    # Second pass: record each entry's verbatim body. An entry runs from the
    # line after its heading up to the next version heading, or end of file.
    for position, entry in enumerate(entries):
        body_start = heading_indices[position] + 1
        body_end = (
            heading_indices[position + 1] if position + 1 < len(heading_indices) else len(lines)
        )
        # Stop at the first stray `##` heading inside this range, so a heading
        # the parser could not read truncates the entry instead of being
        # absorbed into it.
        for stray in terminators:
            if body_start <= stray < body_end:
                body_end = stray
                break
        body_start, body_end = _body_span(lines, body_start, body_end)
        if body_end > body_start:
            entry.raw = "\n".join(lines[body_start:body_end])
            entry.end_line = body_end

    preamble = "\n".join(preamble_lines).strip()

    return Changelog(
        title=title,
        preamble=preamble,
        entries=entries,
        unparsed_headings=unparsed_headings,
    )


@dataclass(frozen=True)
class LintIssue:
    """One problem found in a changelog file.

    Errors mark content the tools will drop or misread. Warnings mark
    conventions worth keeping that do not cost content.
    """

    line: int
    code: str
    severity: str
    message: str

    def __str__(self) -> str:
        return f"{self.line}:{self.severity}:{self.code}: {self.message}"


def lint_changelog(path: Path) -> list[LintIssue]:
    """Check a changelog for content the parser would drop or misattribute.

    The parser is deliberately forgiving -- `changelog get` reproduces an entry
    verbatim, so unrecognised markup still reaches a release body. That
    forgiveness hides mistakes: a `### Security Fixes` heading or a `*` bullet
    is invisible to the structured view, and a malformed `##` heading orphans
    everything under it. This reports those before a release depends on them.

    Returns:
        Issues in line order. Empty means the file is fully understood.
    """
    changelog = parse_changelog(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    issues: list[LintIssue] = []

    # The trailing block of link-reference definitions belongs to the document,
    # not to the last entry. `_body_span` already excludes it from `raw`; the
    # linter stops there too so it does not report the footer as stray content.
    footer = _body_span(lines, 0, len(lines))[1]

    for line_no, text in changelog.unparsed_headings:
        issues.append(
            LintIssue(
                line_no,
                "unparsed-heading",
                "error",
                f"{text!r} is not a version heading; content below it belongs to no entry",
            )
        )

    seen: dict[str, int] = {}
    for entry in changelog.entries:
        if entry.version in seen:
            issues.append(
                LintIssue(
                    entry.start_line,
                    "duplicate-version",
                    "error",
                    f"version {entry.version!r} already defined at line {seen[entry.version]}; "
                    "lookups return the first",
                )
            )
        else:
            seen[entry.version] = entry.start_line
        if not entry.is_unreleased and entry.release_date is None:
            issues.append(
                LintIssue(
                    entry.start_line,
                    "missing-date",
                    "warning",
                    f"released version {entry.version!r} has no date",
                )
            )

    in_entry = False
    section: str | None = None
    section_line = 0
    section_items = 0
    orphan_reported = False
    non_list_reported = False

    def close_section() -> None:
        nonlocal section
        if section is not None and section_items == 0:
            issues.append(
                LintIssue(section_line, "empty-section", "warning", f"### {section} has no items")
            )
        section = None

    for index, line, in_fence in _scan(lines):
        if in_fence or index >= footer:
            continue
        line_no = index + 1

        if VERSION_RE.match(line):
            close_section()
            in_entry = True
            orphan_reported = False
            non_list_reported = False
            continue
        if H2_RE.match(line):
            close_section()
            in_entry = False
            continue
        if not in_entry:
            continue

        if line.startswith("### "):
            close_section()
            section = line[4:].strip()
            section_line = line_no
            section_items = 0
            orphan_reported = False
            non_list_reported = False
            if section not in VALID_SECTIONS:
                issues.append(
                    LintIssue(
                        line_no,
                        "unknown-section",
                        "error",
                        f"{section!r} is not one of {', '.join(sorted(VALID_SECTIONS))}; "
                        "its items are dropped from the structured view",
                    )
                )
            continue

        is_dash = line.startswith("- ")
        is_other_bullet = bool(OTHER_BULLET_RE.match(line))

        if is_other_bullet:
            issues.append(
                LintIssue(
                    line_no,
                    "non-dash-bullet",
                    "error",
                    "list items must start with '- '; this one is dropped from the structured view",
                )
            )

        if is_dash or is_other_bullet:
            if section is None:
                if not orphan_reported:
                    orphan_reported = True
                    issues.append(
                        LintIssue(
                            line_no,
                            "orphan-content",
                            "error",
                            "list item sits under a version heading but outside any "
                            "'### Section', and is dropped from the structured view",
                        )
                    )
            else:
                section_items += 1
            continue

        if not line.strip():
            non_list_reported = False
            continue
        if line.startswith("  "):
            # Indented: a continuation of the item above it.
            continue

        if section is None:
            if not orphan_reported:
                orphan_reported = True
                issues.append(
                    LintIssue(
                        line_no,
                        "orphan-content",
                        "error",
                        "content sits under a version heading but outside any '### Section'",
                    )
                )
        elif not non_list_reported:
            non_list_reported = True
            issues.append(
                LintIssue(
                    line_no,
                    "non-list-content",
                    "warning",
                    "content inside a section is not a list item; it survives in the "
                    "verbatim output but is dropped from the structured view",
                )
            )

    close_section()
    return sorted(issues, key=lambda i: (i.line, i.code))


def unreleased_link_ref(path: Path) -> int | None:
    """Return the 1-indexed line of an `[Unreleased]: <url>` definition, or None.

    The Keep a Changelog template ends with link-reference definitions, and the
    `[Unreleased]` one points at a `compare/vX...HEAD` URL that goes stale the
    moment a release is cut. Rewriting those URLs needs knowledge of the forge
    and its URL shape, so `render_release` leaves them alone; callers use this
    to tell the author the footer still needs a hand edit.
    """
    for index, line, in_fence in _scan(path.read_text(encoding="utf-8").splitlines()):
        if not in_fence and UNRELEASED_LINK_REF_RE.match(line):
            return index + 1
    return None


def render_release(path: Path, version: str, release_date: date) -> str:
    """Return `path`'s text with the `[Unreleased]` content stamped as a release.

    The rewrite inserts a dated `## [version] - YYYY-MM-DD` heading between the
    `## [Unreleased]` heading and its body, leaving `[Unreleased]` in place and
    empty. Nothing else moves: the body keeps its exact bytes, so tables, fenced
    code, and bullet styles the tokenizer does not model survive untouched.

    A date is always written, which is the point -- a heading stamped by this
    function cannot be the undated one the linter rejects.

    Args:
        path: Path to the changelog file.
        version: New version string, e.g. "0.3.0".
        release_date: Date to stamp on the new heading.

    Returns:
        The complete rewritten file text, with the original file's
        trailing-newline state preserved.

    Raises:
        ValueError: If `version` is already present, if there is no
            `[Unreleased]` heading, or if `[Unreleased]` has no content.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    changelog = parse_changelog(path)

    if changelog.get_version(version) is not None:
        raise ValueError(f"version {version!r} is already in {path}")

    unreleased = changelog.get_unreleased()
    if unreleased is None:
        raise ValueError(f"no '## [Unreleased]' heading in {path}")
    if not unreleased.raw.strip():
        raise ValueError(f"'## [Unreleased]' in {path} has nothing to release")

    heading_index = unreleased.start_line - 1
    # Recompute the body's first line rather than assuming it follows the
    # heading directly: parse_changelog trims leading blanks off `raw`.
    body_start, _ = _body_span(lines, heading_index + 1, unreleased.end_line)

    block = [f"## [{version}] - {release_date.isoformat()}", ""]
    if body_start == heading_index + 1:
        # No blank line separated the heading from its body; keep the two
        # headings from colliding.
        block.insert(0, "")

    result = "\n".join(lines[:body_start] + block + lines[body_start:])
    return result + "\n" if text.endswith("\n") else result


def read_project_version(path: Path) -> str | None:
    """Return the static `[project] version` from a pyproject.toml, or None.

    None means "nothing to compare against" rather than "no version": a project
    using `dynamic = ["version"]` has no literal to read, and callers should
    skip the comparison instead of failing on it.
    """
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    if not isinstance(version, str):
        return None
    return version


@dataclass(frozen=True)
class ReleaseProblem:
    """One reason a version is not ready to be released."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def check_release(
    path: Path, version: str, project_version: str | None = None
) -> list[ReleaseProblem]:
    """Check that `version` is ready to be published from `path`.

    This is the gate a tag push runs, and it is stricter than `lint_changelog`
    on purpose. The linter serves any changelog and reports a missing date as a
    warning; here the version being released is about to become a permanent
    record, so an undated, empty, or absent entry is fatal.

    Args:
        path: Path to the changelog file.
        version: Version being released, e.g. "0.3.0".
        project_version: Version declared by the packaging metadata, if it could
            be read. When given, it must equal `version`.

    Returns:
        Problems in the order they were found. Empty means ready to release.
    """
    problems: list[ReleaseProblem] = [
        ReleaseProblem("changelog-lint", f"{path}:{issue.line}: {issue.code}: {issue.message}")
        for issue in lint_changelog(path)
        if issue.severity == "error"
    ]

    entry = parse_changelog(path).get_version(version)
    if entry is None:
        problems.append(
            ReleaseProblem(
                "version-missing",
                f"version {version!r} has no entry in {path}; "
                "run `automate changelog release` before tagging",
            )
        )
    elif entry.is_unreleased:
        problems.append(
            ReleaseProblem(
                "version-unreleased",
                f"{version!r} is the in-progress entry, not a release; "
                "run `automate changelog release <version>` to stamp it",
            )
        )
    else:
        if entry.release_date is None:
            problems.append(
                ReleaseProblem(
                    "missing-date",
                    f"{path}:{entry.start_line}: version {version!r} has no release date",
                )
            )
        if not entry.raw.strip():
            problems.append(
                ReleaseProblem(
                    "empty-entry",
                    f"{path}:{entry.start_line}: version {version!r} has no content; "
                    "the release body would be empty",
                )
            )

    if project_version is not None and project_version != version:
        problems.append(
            ReleaseProblem(
                "version-mismatch",
                f"packaging metadata declares {project_version!r} but the release is {version!r}",
            )
        )

    return problems
