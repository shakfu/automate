"""Tests for the Keep a Changelog parser."""

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from automate.changelog import (
    Changelog,
    ChangelogEntry,
    LintIssue,
    check_release,
    lint_changelog,
    parse_changelog,
    read_project_version,
    render_release,
    unreleased_link_ref,
)


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


class TestRawSlice:
    """Verbatim extraction: `raw` must reproduce the source, not re-render it."""

    def test_raw_preserves_content_to_markdown_drops(self, rich_changelog: Path) -> None:
        cl = parse_changelog(rich_changelog)
        v = cl.get_version("1.0.0")
        assert v is not None

        # All of these are lost by the structured/re-rendered view.
        assert "### Security Fixes" in v.raw
        assert "- Multi-word section heading, not modelled by the tokenizer." in v.raw
        assert "* Star bullet." in v.raw
        assert "| Option | Default |" in v.raw
        assert "| `--verbose` | `false` |" in v.raw

        md = v.to_markdown()
        assert "### Security Fixes" not in md
        assert "* Star bullet." not in md
        assert "| Option | Default |" not in md

    def test_raw_preserves_blank_line_structure(self, rich_changelog: Path) -> None:
        cl = parse_changelog(rich_changelog)
        v = cl.get_version("1.0.0")
        assert v is not None
        # Blank line between the bullet and its indented prose survives, and the
        # fenced block is not glued onto the preceding bullet.
        assert "- Dash bullet with **bold** and `code`.\n\n  Indented prose" in v.raw
        assert "\n\n  ```python\n  print(" in v.raw
        assert "  ```\n" in v.raw

    def test_raw_excludes_version_heading(self, rich_changelog: Path) -> None:
        cl = parse_changelog(rich_changelog)
        v = cl.get_version("1.0.0")
        assert v is not None
        assert "## [1.0.0]" not in v.raw
        assert v.raw.startswith("### Security Fixes")

    def test_raw_stops_at_next_version(self, rich_changelog: Path) -> None:
        cl = parse_changelog(rich_changelog)
        v = cl.get_version("1.0.0")
        assert v is not None
        assert "An older fix." not in v.raw
        assert v.raw.endswith("  - Nested child item.")

    def test_raw_excludes_trailing_link_refs(self, rich_changelog: Path) -> None:
        """The `[1.0.0]: https://...` footer belongs to the document, not the
        last entry whose body happens to run to end of file."""
        cl = parse_changelog(rich_changelog)
        v090 = cl.get_version("0.9.0")
        assert v090 is not None
        assert "https://github.com/owner/repo" not in v090.raw
        assert v090.raw == "### Fixed\n\n- An older fix."

    def test_raw_empty_for_entry_without_body(self, rich_changelog: Path) -> None:
        cl = parse_changelog(rich_changelog)
        unreleased = cl.get_unreleased()
        assert unreleased is not None
        assert unreleased.raw == ""

    def test_line_numbers(self, rich_changelog: Path) -> None:
        lines = rich_changelog.read_text().splitlines()
        cl = parse_changelog(rich_changelog)

        v100 = cl.get_version("1.0.0")
        assert v100 is not None
        assert lines[v100.start_line - 1] == "## [1.0.0] - 2025-01-15"
        assert lines[v100.end_line - 1] == "  - Nested child item."
        assert "\n".join(lines[v100.start_line : v100.end_line]).strip() == v100.raw

        v090 = cl.get_version("0.9.0")
        assert v090 is not None
        assert lines[v090.start_line - 1] == "## [0.9.0] - 2024-06-01"
        assert lines[v090.end_line - 1] == "- An older fix."

    def test_line_numbers_collapse_when_body_empty(self, rich_changelog: Path) -> None:
        cl = parse_changelog(rich_changelog)
        unreleased = cl.get_unreleased()
        assert unreleased is not None
        assert unreleased.end_line == unreleased.start_line

    def test_mid_entry_link_ref_is_kept(self, tmp_path: Path) -> None:
        """Only a *trailing* block of definitions is stripped."""
        content = dedent("""\
            # Changelog

            ## [1.0.0] - 2025-01-01

            [mid]: https://example.com/mid

            ### Added

            - Uses the [mid] reference above.
        """)
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content)
        cl = parse_changelog(p)
        v = cl.get_version("1.0.0")
        assert v is not None
        assert "[mid]: https://example.com/mid" in v.raw

    def test_raw_matches_to_markdown_on_conforming_input(self, simple_changelog: Path) -> None:
        """For input the tokenizer fully models, both views agree."""
        cl = parse_changelog(simple_changelog)
        v = cl.get_version("1.0.0")
        assert v is not None
        assert v.raw == v.to_markdown()

    def test_constructed_entry_has_empty_raw(self) -> None:
        entry = ChangelogEntry(version="1.0.0")
        assert entry.raw == ""
        assert entry.start_line == 0
        assert entry.end_line == 0


class TestHeadingVariants:
    """Keep a Changelog sanctions more heading shapes than `## [x] - date`."""

    def test_inline_linked_heading(self, tmp_path: Path) -> None:
        content = dedent("""\
            # Changelog

            ## [1.0.0](https://github.com/o/r/releases/tag/v1.0.0) - 2025-01-15

            ### Added

            - Linked heading.
        """)
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content)
        cl = parse_changelog(p)
        v = cl.get_version("1.0.0")
        assert v is not None
        assert v.release_date == date(2025, 1, 15)
        assert v.link == "https://github.com/o/r/releases/tag/v1.0.0"
        assert v.raw == "### Added\n\n- Linked heading."

    def test_yanked_heading(self, tmp_path: Path) -> None:
        """The version group must not backtrack across `]` and swallow the
        date and marker into itself."""
        content = dedent("""\
            # Changelog

            ## [1.0.0] - 2025-01-15 [YANKED]

            ### Fixed

            - Yanked release.
        """)
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content)
        cl = parse_changelog(p)
        assert cl.versions == ["1.0.0"]
        v = cl.get_version("1.0.0")
        assert v is not None
        assert v.release_date == date(2025, 1, 15)
        assert v.yanked is True

    def test_linked_and_yanked_together(self, tmp_path: Path) -> None:
        content = dedent("""\
            # Changelog

            ## [1.0.0](https://example.com/v1) - 2025-01-15 [YANKED]

            ### Fixed

            - Both markers.
        """)
        p = tmp_path / "CHANGELOG.md"
        p.write_text(content)
        v = parse_changelog(p).get_version("1.0.0")
        assert v is not None
        assert v.link == "https://example.com/v1"
        assert v.release_date == date(2025, 1, 15)
        assert v.yanked is True

    def test_not_yanked_by_default(self, simple_changelog: Path) -> None:
        v = parse_changelog(simple_changelog).get_version("1.0.0")
        assert v is not None
        assert v.yanked is False
        assert v.link is None


class TestStrayHeadings:
    """A `##` heading the parser cannot read must end the entry above it,
    never extend it."""

    STRAY = dedent("""\
        # Changelog

        ## [Unreleased]

        ### Added

        - Genuinely unreleased.

        ## Types of Changes

        - This belongs to no version.

        ## [1.0.0] - 2025-01-01

        ### Added

        - Released.
    """)

    def test_stray_heading_does_not_leak_into_previous_entry(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(self.STRAY)
        cl = parse_changelog(p)
        unreleased = cl.get_unreleased()
        assert unreleased is not None
        assert unreleased.raw == "### Added\n\n- Genuinely unreleased."
        assert "belongs to no version" not in unreleased.raw
        assert "belongs to no version" not in str(unreleased.sections)

    def test_stray_heading_is_reported(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(self.STRAY)
        cl = parse_changelog(p)
        assert cl.unparsed_headings == [(9, "## Types of Changes")]

    def test_following_entry_is_unaffected(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(self.STRAY)
        v = parse_changelog(p).get_version("1.0.0")
        assert v is not None
        assert v.raw == "### Added\n\n- Released."

    def test_preamble_h2_is_not_treated_as_stray(self, cymongoose_changelog: Path) -> None:
        """Headings before the first version belong to the preamble; the
        Keep a Changelog template ships a 'Types of Changes' section there."""
        cl = parse_changelog(cymongoose_changelog)
        assert cl.unparsed_headings == []
        assert "## Types of Changes" in cl.preamble
        assert cl.versions == ["Unreleased", "0.2.0", "0.1.14"]

    def test_clean_changelog_reports_nothing(self, multi_version_changelog: Path) -> None:
        assert parse_changelog(multi_version_changelog).unparsed_headings == []


class TestLintChangelog:
    """`VALID_SECTIONS` is enforced here rather than in the parser: `raw`
    publishes whatever the author wrote, so the check belongs in a gate the
    author runs, not in a transformation that would silently alter output."""

    def codes(self, path: Path) -> list[str]:
        return [i.code for i in lint_changelog(path)]

    def test_conforming_files_are_clean(
        self, simple_changelog: Path, multi_version_changelog: Path
    ) -> None:
        assert lint_changelog(simple_changelog) == []
        assert lint_changelog(multi_version_changelog) == []

    def test_unknown_section(self, rich_changelog: Path) -> None:
        issues = [i for i in lint_changelog(rich_changelog) if i.code == "unknown-section"]
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "Security Fixes" in issues[0].message

    def test_non_dash_bullet(self, rich_changelog: Path) -> None:
        issues = [i for i in lint_changelog(rich_changelog) if i.code == "non-dash-bullet"]
        assert len(issues) == 1
        assert issues[0].severity == "error"

    def test_non_list_content_is_a_warning(self, rich_changelog: Path) -> None:
        """The table survives in `raw`, so it is not an error -- but it is
        invisible to `sections`, so it is not silent either."""
        issues = [i for i in lint_changelog(rich_changelog) if i.code == "non-list-content"]
        assert len(issues) == 1
        assert issues[0].severity == "warning"

    def test_link_ref_footer_is_not_reported(self, rich_changelog: Path) -> None:
        """The footer belongs to the document; `_body_span` already excludes it."""
        for issue in lint_changelog(rich_changelog):
            assert issue.line < 39, f"reported the link-reference footer: {issue}"

    def test_missing_date_is_a_warning(self, cymongoose_changelog: Path) -> None:
        issues = lint_changelog(cymongoose_changelog)
        assert {i.code for i in issues} == {"missing-date"}
        assert all(i.severity == "warning" for i in issues)
        assert [i.line for i in issues] == [20, 35]

    def test_unreleased_without_date_is_fine(self, simple_changelog: Path) -> None:
        assert "missing-date" not in self.codes(simple_changelog)

    def test_unparsed_heading(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(TestStrayHeadings.STRAY)
        issues = lint_changelog(p)
        assert [i.code for i in issues] == ["unparsed-heading"]
        assert issues[0].line == 9

    def test_duplicate_version(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Changelog

                ## [1.0.0] - 2025-01-01

                ### Added

                - First.

                ## [1.0.0] - 2025-02-01

                ### Added

                - Second, unreachable via get_version.
            """)
        )
        issues = [i for i in lint_changelog(p) if i.code == "duplicate-version"]
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert parse_changelog(p).get_version("1.0.0").raw == "### Added\n\n- First."

    def test_orphan_content(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Changelog

                ## [1.0.0] - 2025-01-01

                - A bullet with no section above it.

                ### Added

                - Fine.
            """)
        )
        issues = [i for i in lint_changelog(p) if i.code == "orphan-content"]
        assert len(issues) == 1
        assert issues[0].line == 5

    def test_empty_section(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Changelog

                ## [1.0.0] - 2025-01-01

                ### Added

                ### Fixed

                - Real.
            """)
        )
        issues = [i for i in lint_changelog(p) if i.code == "empty-section"]
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].line == 5

    def test_fenced_examples_are_not_linted(self, tmp_path: Path) -> None:
        """A changelog documenting the format must not fail its own lint."""
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Changelog

                Example of what not to do:

                ```markdown
                ## [1.0.0]

                ### Bogus Section

                * Star bullet.
                ```

                ## [1.0.0] - 2025-01-01

                ### Added

                - Real.
            """)
        )
        assert lint_changelog(p) == []

    def test_issues_are_sorted_by_line(self, rich_changelog: Path) -> None:
        lines = [i.line for i in lint_changelog(rich_changelog)]
        assert lines == sorted(lines)

    def test_issue_str(self) -> None:
        issue = LintIssue(line=7, code="unknown-section", severity="error", message="nope")
        assert str(issue) == "7:error:unknown-section: nope"


class TestFenceTracking:
    """A `##` line inside a fenced block is an example, not a heading."""

    def test_fenced_example_is_not_parsed_as_structure(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Real Title

                Example of the format:

                ```markdown
                # Not The Title

                ## [9.9.9] - 1999-01-01

                ### Added

                - Not a real entry.
                ```

                ## [1.0.0] - 2025-01-01

                ### Added

                - Real entry.
            """)
        )
        cl = parse_changelog(p)
        assert cl.title == "Real Title"
        assert cl.versions == ["1.0.0"]
        assert cl.unparsed_headings == []
        assert "## [9.9.9] - 1999-01-01" in cl.preamble

    def test_tilde_fence(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Changelog

                ~~~
                ## [9.9.9]
                ~~~

                ## [1.0.0] - 2025-01-01

                ### Added

                - Real.
            """)
        )
        assert parse_changelog(p).versions == ["1.0.0"]

    def test_inner_fence_of_other_kind_does_not_close(self, tmp_path: Path) -> None:
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Changelog

                ````
                ```
                ## [9.9.9]
                ```
                ````

                ## [1.0.0] - 2025-01-01

                ### Added

                - Real.
            """)
        )
        assert parse_changelog(p).versions == ["1.0.0"]

    def test_backticks_in_info_string_do_not_open_a_fence(self, tmp_path: Path) -> None:
        """CommonMark forbids backticks in a backtick fence's info string, so
        such a line is ordinary text and must not swallow the rest of the file."""
        p = tmp_path / "CHANGELOG.md"
        p.write_text(
            dedent("""\
                # Changelog

                ```not`a`fence

                ## [1.0.0] - 2025-01-01

                ### Added

                - Real.
            """)
        )
        assert parse_changelog(p).versions == ["1.0.0"]

    def test_fenced_content_inside_an_entry_survives_in_raw(self, rich_changelog: Path) -> None:
        v = parse_changelog(rich_changelog).get_version("1.0.0")
        assert v is not None
        assert '  print("fenced code inside an entry")' in v.raw


def test_orphan_prose_under_version_heading(tmp_path: Path) -> None:
    p = tmp_path / "CHANGELOG.md"
    p.write_text(
        dedent("""\
            # Changelog

            ## [1.0.0] - 2025-01-01

            Some prose that belongs to no section.

            ### Added

            - Fine.
        """)
    )
    issues = [i for i in lint_changelog(p) if i.code == "orphan-content"]
    assert len(issues) == 1
    assert issues[0].line == 5
    assert issues[0].severity == "error"


@pytest.fixture
def unreleased_rich(tmp_path: Path, rich_changelog: Path) -> Path:
    """A changelog whose [Unreleased] holds rich's unmodelled content.

    rich_changelog's own [Unreleased] is empty, which is the wrong shape for
    exercising a release: dropping the `## [1.0.0]` heading moves that entry's
    tables, fenced code, and star bullets under [Unreleased] instead.
    """
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        rich_changelog.read_text(encoding="utf-8").replace(
            "## [Unreleased]\n\n## [1.0.0] - 2025-01-15\n", "## [Unreleased]\n"
        ),
        encoding="utf-8",
    )
    return target


class TestRenderRelease:
    def test_inserts_dated_heading_below_unreleased(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        out = render_release(target, "0.4.0", date(2026, 8, 26))
        assert "## [Unreleased]\n\n## [0.4.0] - 2026-08-26\n\n### Added" in out

    def test_unreleased_survives_and_is_empty(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        """The next cycle needs somewhere to write, so the heading stays."""
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(render_release(target, "0.4.0", date(2026, 8, 26)), encoding="utf-8")

        changelog = parse_changelog(target)
        unreleased = changelog.get_unreleased()
        assert unreleased is not None
        assert unreleased.raw == ""
        assert changelog.versions == ["Unreleased", "0.4.0", "0.3.0", "0.2.0", "0.1.0"]

    def test_body_is_moved_verbatim(self, unreleased_rich: Path) -> None:
        """The point of inserting a heading rather than rewriting the body: the
        tables, fenced code, and star bullets the tokenizer drops still arrive
        in the release intact."""
        before = parse_changelog(unreleased_rich).get_unreleased()
        assert before is not None
        unreleased_rich.write_text(
            render_release(unreleased_rich, "1.0.0", date(2025, 1, 15)), encoding="utf-8"
        )
        after = parse_changelog(unreleased_rich).get_version("1.0.0")
        assert after is not None
        assert after.raw == before.raw

    def test_result_has_no_missing_date_warning(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        """The regression this command exists to prevent."""
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(render_release(target, "0.4.0", date(2026, 8, 26)), encoding="utf-8")
        assert not [i for i in lint_changelog(target) if i.code == "missing-date"]

    def test_rejects_existing_version(self, tmp_path: Path, multi_version_changelog: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        with pytest.raises(ValueError, match="already in"):
            render_release(target, "0.3.0", date(2026, 8, 26))

    def test_rejects_missing_unreleased(self, tmp_path: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(
            dedent("""\
                # Changelog

                ## [1.0.0] - 2025-01-15

                ### Added

                - Something.
                """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="no '## \\[Unreleased\\]' heading"):
            render_release(target, "1.1.0", date(2026, 8, 26))

    def test_rejects_empty_unreleased(self, simple_changelog: Path) -> None:
        """Releasing nothing yields an empty release body; better to fail."""
        with pytest.raises(ValueError, match="nothing to release"):
            render_release(simple_changelog, "1.1.0", date(2026, 8, 26))

    def test_handles_body_abutting_the_heading(self, tmp_path: Path) -> None:
        """No blank line to reuse, so one has to be added or the two headings
        end up on consecutive lines."""
        target = tmp_path / "CHANGELOG.md"
        target.write_text(
            "# Changelog\n\n## [Unreleased]\n### Added\n\n- Something.\n", encoding="utf-8"
        )
        out = render_release(target, "1.0.0", date(2026, 8, 26))
        assert out == (
            "# Changelog\n\n## [Unreleased]\n\n"
            "## [1.0.0] - 2026-08-26\n\n### Added\n\n- Something.\n"
        )

    def test_preserves_absent_trailing_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(
            "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Something.", encoding="utf-8"
        )
        assert not render_release(target, "1.0.0", date(2026, 8, 26)).endswith("\n")

    def test_preserves_trailing_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(
            "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Something.\n", encoding="utf-8"
        )
        assert render_release(target, "1.0.0", date(2026, 8, 26)).endswith("- Something.\n")


class TestUnreleasedLinkRef:
    def test_finds_footer_definition(self, rich_changelog: Path) -> None:
        assert unreleased_link_ref(rich_changelog) == 39

    def test_absent_returns_none(self, simple_changelog: Path) -> None:
        assert unreleased_link_ref(simple_changelog) is None

    def test_ignores_definitions_inside_fences(self, tmp_path: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(
            dedent("""\
                # Changelog

                ```markdown
                [Unreleased]: https://example.com/compare/v1.0.0...HEAD
                ```

                ## [Unreleased]
                """),
            encoding="utf-8",
        )
        assert unreleased_link_ref(target) is None


class TestReadProjectVersion:
    def test_reads_static_version(self, tmp_path: Path) -> None:
        target = tmp_path / "pyproject.toml"
        target.write_text('[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")
        assert read_project_version(target) == "1.2.3"

    def test_dynamic_version_is_none(self, tmp_path: Path) -> None:
        """setuptools-scm and friends have no literal to compare against, so
        the caller must skip the check rather than fail it."""
        target = tmp_path / "pyproject.toml"
        target.write_text('[project]\nname = "x"\ndynamic = ["version"]\n', encoding="utf-8")
        assert read_project_version(target) is None

    def test_missing_project_table_is_none(self, tmp_path: Path) -> None:
        target = tmp_path / "pyproject.toml"
        target.write_text('[build-system]\nrequires = ["hatchling"]\n', encoding="utf-8")
        assert read_project_version(target) is None


class TestCheckRelease:
    def test_clean_entry_has_no_problems(self, multi_version_changelog: Path) -> None:
        assert check_release(multi_version_changelog, "0.3.0") == []

    def test_matching_project_version_has_no_problems(self, multi_version_changelog: Path) -> None:
        assert check_release(multi_version_changelog, "0.3.0", "0.3.0") == []

    def test_missing_version(self, multi_version_changelog: Path) -> None:
        codes = [p.code for p in check_release(multi_version_changelog, "9.9.9")]
        assert codes == ["version-missing"]

    def test_unreleased_is_not_a_release(self, multi_version_changelog: Path) -> None:
        """Tagging `vUnreleased` is absurd, but a tag of the literal string is
        not, and the resulting entry would be undated by definition."""
        codes = [p.code for p in check_release(multi_version_changelog, "Unreleased")]
        assert codes == ["version-unreleased"]

    def test_missing_date_is_fatal_here(self, cymongoose_changelog: Path) -> None:
        """The linter calls this a warning; publishing it is not negotiable."""
        undated = next(
            e.version
            for e in parse_changelog(cymongoose_changelog).entries
            if not e.is_unreleased and e.release_date is None
        )
        codes = [p.code for p in check_release(cymongoose_changelog, undated)]
        assert "missing-date" in codes

    def test_empty_entry(self, tmp_path: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(
            "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2025-01-15\n", encoding="utf-8"
        )
        codes = [p.code for p in check_release(target, "1.0.0")]
        assert codes == ["empty-entry"]

    def test_reports_lint_errors(self, rich_changelog: Path) -> None:
        problems = check_release(rich_changelog, "1.0.0")
        assert [p.code for p in problems] == ["changelog-lint"] * len(problems)
        assert problems

    def test_version_mismatch(self, multi_version_changelog: Path) -> None:
        problems = check_release(multi_version_changelog, "0.3.0", "0.2.0")
        assert [p.code for p in problems] == ["version-mismatch"]
        assert "'0.2.0'" in problems[0].message

    def test_problem_str_is_code_prefixed(self, multi_version_changelog: Path) -> None:
        problem = check_release(multi_version_changelog, "9.9.9")[0]
        assert str(problem).startswith("version-missing: ")
