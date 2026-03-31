"""Tests for the Keep a Changelog parser."""

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from automate.changelog import Changelog, ChangelogEntry, parse_changelog


class TestChangelogEntry:
    def test_is_unreleased(self) -> None:
        entry = ChangelogEntry(version="Unreleased")
        assert entry.is_unreleased is True

    def test_is_not_unreleased(self) -> None:
        entry = ChangelogEntry(version="1.0.0", release_date=date(2025, 1, 15))
        assert entry.is_unreleased is False

    def test_to_markdown(self) -> None:
        entry = ChangelogEntry(
            version="1.0.0",
            release_date=date(2025, 1, 15),
            sections={
                "Added": ["Feature A.", "Feature B."],
                "Fixed": ["Bug fix."],
            },
        )
        md = entry.to_markdown()
        assert "### Added" in md
        assert "- Feature A." in md
        assert "- Feature B." in md
        assert "### Fixed" in md
        assert "- Bug fix." in md

    def test_to_markdown_empty_sections(self) -> None:
        entry = ChangelogEntry(version="Unreleased")
        assert entry.to_markdown() == ""


class TestChangelog:
    def test_get_version_found(self) -> None:
        entry = ChangelogEntry(version="1.0.0")
        cl = Changelog(title="Changelog", preamble="", entries=[entry])
        assert cl.get_version("1.0.0") is entry

    def test_get_version_not_found(self) -> None:
        cl = Changelog(title="Changelog", preamble="", entries=[])
        assert cl.get_version("9.9.9") is None

    def test_get_unreleased(self) -> None:
        unreleased = ChangelogEntry(version="Unreleased")
        released = ChangelogEntry(version="1.0.0")
        cl = Changelog(title="Changelog", preamble="", entries=[unreleased, released])
        assert cl.get_unreleased() is unreleased

    def test_get_unreleased_missing(self) -> None:
        cl = Changelog(title="Changelog", preamble="", entries=[])
        assert cl.get_unreleased() is None

    def test_versions(self) -> None:
        entries = [
            ChangelogEntry(version="Unreleased"),
            ChangelogEntry(version="0.2.0"),
            ChangelogEntry(version="0.1.0"),
        ]
        cl = Changelog(title="Changelog", preamble="", entries=entries)
        assert cl.versions == ["Unreleased", "0.2.0", "0.1.0"]


class TestParseChangelog:
    def test_parse_simple(self, simple_changelog: Path) -> None:
        cl = parse_changelog(simple_changelog)
        assert cl.title == "Changelog"
        assert "Keep a Changelog" in cl.preamble
        assert len(cl.entries) == 2  # Unreleased + 1.0.0

        unreleased = cl.get_unreleased()
        assert unreleased is not None
        assert unreleased.sections == {}

        v100 = cl.get_version("1.0.0")
        assert v100 is not None
        assert v100.release_date == date(2025, 1, 15)
        assert "Added" in v100.sections
        assert len(v100.sections["Added"]) == 2
        assert "Fixed" in v100.sections
        assert len(v100.sections["Fixed"]) == 1

    def test_parse_multi_version(self, multi_version_changelog: Path) -> None:
        cl = parse_changelog(multi_version_changelog)
        assert cl.title == "Changelog"
        assert len(cl.entries) == 4  # Unreleased + 0.3.0 + 0.2.0 + 0.1.0

        assert cl.versions == ["Unreleased", "0.3.0", "0.2.0", "0.1.0"]

        unreleased = cl.get_unreleased()
        assert unreleased is not None
        assert "Added" in unreleased.sections
        assert len(unreleased.sections["Added"]) == 1

        v030 = cl.get_version("0.3.0")
        assert v030 is not None
        assert v030.release_date == date(2025, 6, 1)
        assert "Added" in v030.sections
        assert "Changed" in v030.sections
        assert "Deprecated" in v030.sections
        assert len(v030.sections["Added"]) == 2
        assert len(v030.sections["Changed"]) == 2
        assert len(v030.sections["Deprecated"]) == 1

        v020 = cl.get_version("0.2.0")
        assert v020 is not None
        assert "Security" in v020.sections

    def test_parse_cymongoose(self, cymongoose_changelog: Path) -> None:
        cl = parse_changelog(cymongoose_changelog)
        assert cl.title == "CHANGELOG"
        assert len(cl.entries) == 3  # Unreleased + 0.2.0 + 0.1.14

        v020 = cl.get_version("0.2.0")
        assert v020 is not None
        assert v020.release_date is None  # cymongoose 0.2.0 has no date
        assert "Added" in v020.sections
        assert "Fixed" in v020.sections
        assert "Security" in v020.sections
        assert len(v020.sections["Added"]) == 2

        v0114 = cl.get_version("0.1.14")
        assert v0114 is not None
        assert "Changed" in v0114.sections
        assert "Fixed" in v0114.sections
        assert "Security" in v0114.sections

    def test_parse_preamble_preserved(self, cymongoose_changelog: Path) -> None:
        cl = parse_changelog(cymongoose_changelog)
        assert "Keep a Changelog" in cl.preamble
        assert "Commons Changelog" in cl.preamble

    def test_entry_to_markdown_roundtrip(self, simple_changelog: Path) -> None:
        cl = parse_changelog(simple_changelog)
        v100 = cl.get_version("1.0.0")
        assert v100 is not None
        md = v100.to_markdown()
        assert "### Added" in md
        assert "- Initial release with core functionality." in md
        assert "### Fixed" in md
        assert "- Resolved startup crash on Windows." in md

    def test_parse_no_title_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.md"
        bad.write_text("No heading here\n\n## [1.0.0]\n")
        with pytest.raises(ValueError, match="No title heading"):
            parse_changelog(bad)

    def test_parse_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_changelog(tmp_path / "nonexistent.md")

    def test_multiline_item(self, tmp_path: Path) -> None:
        content = dedent("""\
            # Changelog

            ## [1.0.0] - 2025-01-01

            ### Fixed

            - First line of a fix.
              Continuation of the fix description.
            - Second fix.
        """)
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content)
        cl = parse_changelog(p)
        v = cl.get_version("1.0.0")
        assert v is not None
        assert len(v.sections["Fixed"]) == 2
        assert "Continuation" in v.sections["Fixed"][0]

    def test_empty_unreleased(self, tmp_path: Path) -> None:
        content = dedent("""\
            # Changelog

            ## [Unreleased]
        """)
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content)
        cl = parse_changelog(p)
        assert len(cl.entries) == 1
        unreleased = cl.get_unreleased()
        assert unreleased is not None
        assert unreleased.sections == {}
