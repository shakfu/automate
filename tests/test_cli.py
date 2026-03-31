"""Tests for the CLI commands."""

from pathlib import Path

from click.testing import CliRunner

from automate.cli import cli


class TestVersion:
    def test_version_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


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

    def test_get_plain_format(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["changelog", "get", "1.0.0", "-f", str(simple_changelog), "--format", "plain"]
        )
        assert result.exit_code == 0
        assert "**" not in result.output

    def test_get_cymongoose_version(self, cymongoose_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["changelog", "get", "0.2.0", "-f", str(cymongoose_changelog)]
        )
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
        result = runner.invoke(
            cli, ["release-body", "1.0.0", "-f", str(simple_changelog)]
        )
        assert result.exit_code == 0
        assert "## Changes since the last release" in result.output
        # No description paragraph before the changes heading
        lines = result.output.strip().splitlines()
        assert lines[0] == "## Changes since the last release"

    def test_release_body_missing_version(self, simple_changelog: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["release-body", "9.9.9", "-f", str(simple_changelog)]
        )
        assert result.exit_code != 0
        assert "not found" in result.output
