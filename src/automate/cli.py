"""CLI entry point for automate."""

from pathlib import Path

import click

from automate import __version__
from automate.changelog import parse_changelog


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """automate - CI/CD helpers for Python projects."""


@cli.group()
def changelog() -> None:
    """Changelog parsing commands."""


@changelog.command("get")
@click.argument("version")
@click.option(
    "--file",
    "-f",
    "filepath",
    default="CHANGELOG.md",
    type=click.Path(exists=True, path_type=Path),
    help="Path to the changelog file.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "plain"]),
    default="markdown",
    help="Output format.",
)
def changelog_get(version: str, filepath: Path, fmt: str) -> None:
    """Extract changelog entry for VERSION (e.g. '0.2.0' or 'Unreleased')."""
    cl = parse_changelog(filepath)
    entry = cl.get_version(version)
    if entry is None:
        raise click.ClickException(f"Version '{version}' not found in {filepath}")
    if fmt == "markdown":
        click.echo(entry.to_markdown())
    else:
        # Plain: strip markdown bold markers
        text = entry.to_markdown()
        text = text.replace("**", "")
        click.echo(text)


@changelog.command("list")
@click.option(
    "--file",
    "-f",
    "filepath",
    default="CHANGELOG.md",
    type=click.Path(exists=True, path_type=Path),
    help="Path to the changelog file.",
)
def changelog_list(filepath: Path) -> None:
    """List all versions in the changelog."""
    cl = parse_changelog(filepath)
    for entry in cl.entries:
        date_str = f"  {entry.release_date}" if entry.release_date else ""
        click.echo(f"{entry.version}{date_str}")


@cli.command("release-body")
@click.argument("version")
@click.option(
    "--file",
    "-f",
    "filepath",
    default="CHANGELOG.md",
    type=click.Path(exists=True, path_type=Path),
    help="Path to the changelog file.",
)
@click.option(
    "--description",
    "-d",
    default="",
    help="Project description paragraph for the release body.",
)
def release_body(version: str, filepath: Path, description: str) -> None:
    """Generate a GitHub Release body for VERSION.

    Outputs markdown combining the project description and changelog entry,
    suitable for passing to `gh release create --notes-file`.
    """
    cl = parse_changelog(filepath)
    entry = cl.get_version(version)
    if entry is None:
        raise click.ClickException(f"Version '{version}' not found in {filepath}")

    parts: list[str] = []

    if description:
        parts.append(description)
        parts.append("")

    parts.append("## Changes since the last release")
    parts.append("")
    parts.append(entry.to_markdown())

    click.echo("\n".join(parts))
