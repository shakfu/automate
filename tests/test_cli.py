"""Tests for the CLI commands."""

import subprocess
import sys
from datetime import date
from importlib.metadata import version as metadata_version
from pathlib import Path

from click.testing import CliRunner

from automate import __version__
from automate.changelog import read_project_version
from automate.cli import cli


class TestVersion:
    def test_version_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_version_comes_from_package_metadata(self) -> None:
        """Asserted against installed metadata rather than a literal, so a
        version bump does not fail here instead of where it was made."""
        assert __version__ == metadata_version("automate")
        assert __version__ != "0.0.0+unknown"


class TestChangelogGet:
    def test_get_existing_version(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "get", "1.0.0", "-f", str(simple_changelog)])
        assert result.exit_code == 0
        assert "### Added" in result.output
        assert "Initial release with core functionality." in result.output
        assert "### Fixed" in result.output

    def test_get_unreleased(self, multi_version_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["changelog", "get", "Unreleased", "-f", str(multi_version_changelog)]
        )
        assert result.exit_code == 0
        assert "async support" in result.output

    def test_get_missing_version(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "get", "9.9.9", "-f", str(simple_changelog)])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_get_plain_format(self, cymongoose_changelog: Path) -> None:
        """cymongoose's entries contain bold markers, so this actually exercises
        the transformation; changelog_simple.md has none and passed vacuously."""
        runner = CliRunner()
        markdown = CliRunner().invoke(
            cli, ["changelog", "get", "0.2.0", "-f", str(cymongoose_changelog)]
        )
        assert "**" in markdown.output

        result = runner.invoke(
            cli, ["changelog", "get", "0.2.0", "-f", str(cymongoose_changelog), "--format", "plain"]
        )
        assert result.exit_code == 0
        assert "**" not in result.output
        assert "serve_dir" in result.output

    def test_get_cymongoose_version(self, cymongoose_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "get", "0.2.0", "-f", str(cymongoose_changelog)])
        assert result.exit_code == 0
        assert "serve_dir" in result.output
        assert "### Added" in result.output
        assert "### Security" in result.output


class TestChangelogList:
    def test_list_versions(self, multi_version_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "list", "-f", str(multi_version_changelog)])
        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert lines[0] == "Unreleased"
        assert "0.3.0" in lines[1]
        assert "2025-06-01" in lines[1]
        assert "0.2.0" in lines[2]
        assert "0.1.0" in lines[3]

    def test_list_simple(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "list", "-f", str(simple_changelog)])
        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert len(lines) == 2
        assert "Unreleased" in lines[0]
        assert "1.0.0" in lines[1]


class TestReleaseBody:
    def test_release_body_with_description(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "release-body",
                "1.0.0",
                "-f",
                str(simple_changelog),
                "-d",
                "A tool for doing things.",
            ],
        )
        assert result.exit_code == 0
        assert "A tool for doing things." in result.output
        assert "## Changes since the last release" in result.output
        assert "### Added" in result.output
        assert "Initial release with core functionality." in result.output

    def test_release_body_no_description(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["release-body", "1.0.0", "-f", str(simple_changelog)])
        assert result.exit_code == 0
        assert "## Changes since the last release" in result.output
        # No description paragraph before the changes heading
        lines = result.output.strip().splitlines()
        assert lines[0] == "## Changes since the last release"

    def test_release_body_missing_version(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["release-body", "9.9.9", "-f", str(simple_changelog)])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestVerbatimOutput:
    """`changelog get` and `release-body` publish the source text as written."""

    def test_get_preserves_unmodelled_content(self, rich_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "get", "1.0.0", "-f", str(rich_changelog)])
        assert result.exit_code == 0
        assert "### Security Fixes" in result.output
        assert "* Star bullet." in result.output
        assert "| Option | Default |" in result.output
        assert '  print("fenced code inside an entry")' in result.output

    def test_get_does_not_leak_neighbouring_entries(self, rich_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "get", "1.0.0", "-f", str(rich_changelog)])
        assert result.exit_code == 0
        assert "An older fix." not in result.output
        assert "## [0.9.0]" not in result.output

    def test_get_last_entry_excludes_link_ref_footer(self, rich_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "get", "0.9.0", "-f", str(rich_changelog)])
        assert result.exit_code == 0
        assert "An older fix." in result.output
        assert "https://github.com/owner/repo" not in result.output

    def test_release_body_preserves_unmodelled_content(self, rich_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["release-body", "1.0.0", "-f", str(rich_changelog), "-d", "A tool."],
        )
        assert result.exit_code == 0
        assert result.output.startswith("A tool.\n\n## Changes since the last release")
        assert "### Security Fixes" in result.output
        assert "| Option | Default |" in result.output

    def test_get_empty_entry_outputs_nothing(self, rich_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", "get", "Unreleased", "-f", str(rich_changelog)])
        assert result.exit_code == 0
        assert result.output.strip() == ""


class TestModuleEntryPoint:
    def test_python_m_automate_runs(self) -> None:
        """`python -m automate` must work, and importing __main__ must not."""
        result = subprocess.run(
            [sys.executable, "-m", "automate", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert __version__ in result.stdout

    def test_importing_main_does_not_execute_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import automate.__main__; print('imported')"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "imported"


class TestChangelogLint:
    def test_clean_file_exits_zero(self, simple_changelog: Path) -> None:
        result = CliRunner().invoke(cli, ["changelog", "lint", "-f", str(simple_changelog)])
        assert result.exit_code == 0
        assert "no issues" in result.output

    def test_errors_exit_nonzero(self, rich_changelog: Path) -> None:
        result = CliRunner().invoke(cli, ["changelog", "lint", "-f", str(rich_changelog)])
        assert result.exit_code == 1
        assert "unknown-section" in result.output
        assert "non-dash-bullet" in result.output

    def test_warnings_alone_exit_zero(self, cymongoose_changelog: Path) -> None:
        result = CliRunner().invoke(cli, ["changelog", "lint", "-f", str(cymongoose_changelog)])
        assert result.exit_code == 0
        assert "missing-date" in result.output

    def test_strict_promotes_warnings(self, cymongoose_changelog: Path) -> None:
        result = CliRunner().invoke(
            cli, ["changelog", "lint", "-f", str(cymongoose_changelog), "--strict"]
        )
        assert result.exit_code == 1

    def test_output_is_file_line_prefixed(self, rich_changelog: Path) -> None:
        """Prefixed so editors and CI annotations can jump to the line."""
        result = CliRunner().invoke(cli, ["changelog", "lint", "-f", str(rich_changelog)])
        assert f"{rich_changelog}:9: error: unknown-section:" in result.output


class TestSelfLint:
    def test_this_project_changelog_is_clean(self) -> None:
        """Dogfooding: automate's own CHANGELOG must pass its own linter."""
        changelog = Path(__file__).parent.parent / "CHANGELOG.md"
        result = CliRunner().invoke(cli, ["changelog", "lint", "-f", str(changelog), "--strict"])
        assert result.exit_code == 0, result.output


class TestChangelogRelease:
    def test_writes_dated_heading(self, tmp_path: Path, multi_version_changelog: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            ["changelog", "release", "0.4.0", "-f", str(target), "--date", "2026-08-26"],
        )
        assert result.exit_code == 0, result.output
        assert "## [0.4.0] - 2026-08-26" in target.read_text(encoding="utf-8")
        assert "released 0.4.0 (2026-08-26)" in result.output

    def test_defaults_to_today(self, tmp_path: Path, multi_version_changelog: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        result = CliRunner().invoke(cli, ["changelog", "release", "0.4.0", "-f", str(target)])
        assert result.exit_code == 0, result.output
        assert f"## [0.4.0] - {date.today().isoformat()}" in target.read_text(encoding="utf-8")

    def test_dry_run_leaves_the_file_alone(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        target = tmp_path / "CHANGELOG.md"
        original = multi_version_changelog.read_text(encoding="utf-8")
        target.write_text(original, encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            [
                "changelog",
                "release",
                "0.4.0",
                "-f",
                str(target),
                "--date",
                "2026-08-26",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert target.read_text(encoding="utf-8") == original
        assert "## [0.4.0] - 2026-08-26" in result.output

    def test_refuses_empty_unreleased(self, tmp_path: Path, simple_changelog: Path) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(simple_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        result = CliRunner().invoke(
            cli, ["changelog", "release", "1.1.0", "-f", str(target), "--date", "2026-08-26"]
        )
        assert result.exit_code != 0
        assert "nothing to release" in result.output

    def test_notes_stale_unreleased_link_definition(
        self, tmp_path: Path, rich_changelog: Path
    ) -> None:
        """The footer's compare URL still points at the previous release; the
        rewrite cannot guess the forge's URL shape, so it says so instead."""
        target = tmp_path / "CHANGELOG.md"
        target.write_text(
            rich_changelog.read_text(encoding="utf-8").replace(
                "## [Unreleased]\n\n## [1.0.0] - 2025-01-15\n", "## [Unreleased]\n"
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli, ["changelog", "release", "1.0.0", "-f", str(target), "--date", "2025-01-15"]
        )
        assert result.exit_code == 0, result.output
        assert "[Unreleased] link definition" in result.output

    def test_notes_pyproject_version_drift(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nversion = "0.3.0"\n', encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            [
                "changelog",
                "release",
                "0.4.0",
                "-f",
                str(target),
                "--date",
                "2026-08-26",
                "--pyproject",
                str(pyproject),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "version is '0.3.0', not '0.4.0'" in result.output

    def test_silent_when_pyproject_agrees(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        target = tmp_path / "CHANGELOG.md"
        target.write_text(multi_version_changelog.read_text(encoding="utf-8"), encoding="utf-8")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nversion = "0.4.0"\n', encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            [
                "changelog",
                "release",
                "0.4.0",
                "-f",
                str(target),
                "--date",
                "2026-08-26",
                "--pyproject",
                str(pyproject),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "note:" not in result.output


class TestCheckRelease:
    def test_ready_version_exits_zero(self, multi_version_changelog: Path) -> None:
        result = CliRunner().invoke(
            cli,
            ["check-release", "0.3.0", "-f", str(multi_version_changelog), "--no-pyproject"],
        )
        assert result.exit_code == 0, result.output
        assert "ready to release" in result.output

    def test_missing_version_exits_nonzero(self, multi_version_changelog: Path) -> None:
        result = CliRunner().invoke(
            cli,
            ["check-release", "9.9.9", "-f", str(multi_version_changelog), "--no-pyproject"],
        )
        assert result.exit_code == 1
        assert "version-missing:" in result.output
        assert "1 problem(s)" in result.output

    def test_undated_version_exits_nonzero(self, cymongoose_changelog: Path) -> None:
        """The exact failure this command was added to catch before publishing
        rather than after."""
        result = CliRunner().invoke(
            cli,
            ["check-release", "0.2.0", "-f", str(cymongoose_changelog), "--no-pyproject"],
        )
        assert result.exit_code == 1
        assert "missing-date:" in result.output

    def test_pyproject_mismatch_exits_nonzero(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nversion = "0.2.0"\n', encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            [
                "check-release",
                "0.3.0",
                "-f",
                str(multi_version_changelog),
                "--pyproject",
                str(pyproject),
            ],
        )
        assert result.exit_code == 1
        assert "version-mismatch:" in result.output

    def test_absent_pyproject_is_skipped(
        self, tmp_path: Path, multi_version_changelog: Path
    ) -> None:
        """Consumer projects need not be Python packages built from a
        pyproject.toml, so a missing file is not a problem to report."""
        result = CliRunner().invoke(
            cli,
            [
                "check-release",
                "0.3.0",
                "-f",
                str(multi_version_changelog),
                "--pyproject",
                str(tmp_path / "absent.toml"),
            ],
        )
        assert result.exit_code == 0, result.output


class TestSelfRelease:
    def test_this_project_is_releasable_at_its_declared_version(self) -> None:
        """Dogfooding: pyproject's version must have a dated, non-empty entry.

        This is the invariant the v0.2.0 commit broke -- the heading was written
        by hand and the date was left off -- and it holds only if the version
        bump and the changelog stamp land together.
        """
        root = Path(__file__).parent.parent
        version = read_project_version(root / "pyproject.toml")
        assert version is not None
        result = CliRunner().invoke(
            cli,
            [
                "check-release",
                version,
                "-f",
                str(root / "CHANGELOG.md"),
                "--pyproject",
                str(root / "pyproject.toml"),
            ],
        )
        assert result.exit_code == 0, result.output
