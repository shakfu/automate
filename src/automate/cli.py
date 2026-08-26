"""CLI entry point for automate."""

import datetime
from pathlib import Path

import click

from automate import __version__
from automate.changelog import (
    check_release,
    lint_changelog,
    parse_changelog,
    read_project_version,
    render_release,
    unreleased_link_ref,
)

# Repeated verbatim on every command that reads a changelog.
FILE_OPTION = click.option(
    "--file",
    "-f",
    "filepath",
    default="CHANGELOG.md",
    type=click.Path(exists=True, path_type=Path),
    help="Path to the changelog file.",
)


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """automate - CI/CD helpers for Python projects."""


@cli.group()
def changelog() -> None:
    """Changelog parsing commands."""


@changelog.command("get")
@click.argument("version")
@FILE_OPTION
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "plain"]),
    default="markdown",
    help="Output format.",
)
def changelog_get(version: str, filepath: Path, fmt: str) -> None:
    """Extract changelog entry for VERSION (e.g. '0.2.0' or 'Unreleased').

    The entry is reproduced verbatim from the source file, so tables, fenced
    code, and non-standard section headings are preserved as written.
    """
    cl = parse_changelog(filepath)
    entry = cl.get_version(version)
    if entry is None:
        raise click.ClickException(f"Version '{version}' not found in {filepath}")
    if fmt == "markdown":
        click.echo(entry.raw)
    else:
        # Plain: strip markdown bold markers
        click.echo(entry.raw.replace("**", ""))


@changelog.command("list")
@FILE_OPTION
def changelog_list(filepath: Path) -> None:
    """List all versions in the changelog."""
    cl = parse_changelog(filepath)
    for entry in cl.entries:
        date_str = f"  {entry.release_date}" if entry.release_date else ""
        click.echo(f"{entry.version}{date_str}")


@cli.command("release-body")
@click.argument("version")
@FILE_OPTION
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
    parts.append(entry.raw)

    click.echo("\n".join(parts))


@changelog.command("lint")
@FILE_OPTION
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors.",
)
def changelog_lint(filepath: Path, strict: bool) -> None:
    """Report content the parser would drop or misattribute.

    Exits non-zero when errors are found, so a release workflow can gate on it.
    Warnings do not fail the run unless --strict is given.
    """
    issues = lint_changelog(filepath)
    if not issues:
        click.echo(f"{filepath}: no issues")
        return

    for issue in issues:
        click.echo(f"{filepath}:{issue.line}: {issue.severity}: {issue.code}: {issue.message}")

    errors = sum(1 for i in issues if i.severity == "error")
    warnings = len(issues) - errors
    click.echo(f"{errors} error(s), {warnings} warning(s)", err=True)
    if errors or (strict and warnings):
        raise SystemExit(1)


@changelog.command("release")
@click.argument("version")
@FILE_OPTION
@click.option(
    "--date",
    "release_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Release date to stamp (default: today).",
)
@click.option(
    "--pyproject",
    "pyproject_path",
    default="pyproject.toml",
    type=click.Path(path_type=Path),
    help="Packaging metadata to cross-check the version against.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the rewritten changelog instead of writing it.",
)
def changelog_release(
    version: str,
    filepath: Path,
    release_date: datetime.datetime | None,
    pyproject_path: Path,
    dry_run: bool,
) -> None:
    """Stamp the [Unreleased] content as released VERSION.

    Inserts a dated `## [VERSION] - YYYY-MM-DD` heading below `## [Unreleased]`
    and leaves the body where it is, so the entry's exact text is preserved.
    Doing this by hand is where release metadata goes missing; doing it here
    cannot produce an undated heading.
    """
    stamp = release_date.date() if release_date else datetime.date.today()
    try:
        rewritten = render_release(filepath, version, stamp)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        click.echo(rewritten, nl=False)
        return

    filepath.write_text(rewritten, encoding="utf-8")
    click.echo(f"{filepath}: released {version} ({stamp.isoformat()})")

    link_line = unreleased_link_ref(filepath)
    if link_line is not None:
        click.echo(
            f"{filepath}:{link_line}: note: the [Unreleased] link definition still points at "
            f"the previous release; add a [{version}] definition and retarget it",
            err=True,
        )

    if pyproject_path.exists():
        project_version = read_project_version(pyproject_path)
        if project_version is not None and project_version != version:
            click.echo(
                f"{pyproject_path}: note: version is {project_version!r}, not {version!r}; "
                "bump it before tagging or `automate check-release` will fail",
                err=True,
            )


@cli.command("check-release")
@click.argument("version")
@FILE_OPTION
@click.option(
    "--pyproject",
    "pyproject_path",
    default="pyproject.toml",
    type=click.Path(path_type=Path),
    help="Packaging metadata to cross-check the version against.",
)
@click.option(
    "--no-pyproject",
    is_flag=True,
    help="Skip the packaging-metadata version check.",
)
def check_release_command(
    version: str, filepath: Path, pyproject_path: Path, no_pyproject: bool
) -> None:
    """Verify VERSION is ready to be published, then exit non-zero if not.

    Stricter than `changelog lint`: the entry must exist, carry a date, and have
    content, and the packaging metadata must agree on the version. Run it from a
    tag push so a bad release fails before it is published rather than after.
    """
    project_version = None
    if not no_pyproject and pyproject_path.exists():
        project_version = read_project_version(pyproject_path)

    problems = check_release(filepath, version, project_version)
    if not problems:
        click.echo(f"{filepath}: {version} is ready to release")
        return

    for problem in problems:
        click.echo(str(problem))
    click.echo(f"{len(problems)} problem(s); {version} is not ready to release", err=True)
    raise SystemExit(1)
