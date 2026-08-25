"""Tests for the CLI commands."""

import subprocess
import sys
from importlib.metadata import version as metadata_version
from pathlib import Path

from click.testing import CliRunner

from automate import __version__
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
