# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `automate changelog release VERSION`: stamps the accumulated `[Unreleased]` content as a dated release entry. The heading is inserted above the existing body rather than the body being re-rendered, so unmodelled markup survives byte for byte, and a date is always written -- the undated heading this project shipped in 0.2.0 cannot be produced by the command.

- `automate check-release VERSION`: verifies one version is publishable -- the entry exists, carries a date, and has content, `pyproject.toml` agrees on the version, and the file has no error-severity lint issues. Stricter than `changelog lint`, which serves any changelog and so reports a missing date as a warning; here the entry is about to become a permanent release record.

- `reusable-release.yml` runs `check-release` against the tagged version before generating the release body (`verify-release`, default true; `pyproject-path`, default `pyproject.toml`). A tag whose changelog entry is missing, undated, or empty now fails before the release is published rather than after.

- `make release` and `make check-release`, both defaulting `VERSION` to what `pyproject.toml` declares.

- `tests/test_cli.py::TestSelfRelease`: asserts this project's declared version is publishable, so a version bump landing without its changelog stamp fails CI.

### Fixed

- `CHANGELOG.md`: the 0.2.0 heading carried no date, which failed the project's own `changelog lint --strict` dogfooding test on every branch.

## [0.2.0] - 2026-08-26

### Added

- `automate changelog lint`: reports content the parser would drop or misattribute (unknown sections, `*` bullets, orphan content, duplicate versions, unparsed `##` headings, missing dates, empty sections). Exits non-zero on errors so a release can gate on it; `--strict` also fails on warnings. This is where `VALID_SECTIONS` is now enforced -- the parser stays forgiving because `raw` publishes what the author wrote, so the check belongs in a gate the author runs rather than in a transformation that silently alters output.

- `reusable-release.yml` runs the linter before generating a release body (`lint-changelog`, default true).

- `.github/dependabot.yml`, covering GitHub Actions and uv.

- `make format-check` and `make workflows`; `make qa` now runs lint, format-check, typecheck, actionlint, and tests.

- `tests/test_workflows.py`: structural checks over `.github/workflows/`, including a guard that fails if any expression is interpolated into a `run:` body outside the two inputs that are shell commands by definition. Verified to catch all 16 pre-existing occurrences.

- actionlint job in `ci.yml`, pinned to `rhysd/actionlint:1.7.12`.

- `ChangelogEntry.raw`, `ChangelogEntry.start_line`, and `ChangelogEntry.end_line`: verbatim entry text and its source span.

### Changed

- **Breaking:** `reusable-ci.yml` no longer has a separate `coverage` job; coverage is collected inside the test job. A branch protection rule requiring the "Coverage" check must be updated.

- **Breaking:** `reusable-ci.yml` defaults `os-matrix` to `["ubuntu-latest"]`. The matrix is a cross product, so the previous three-OS default meant 15 jobs for a pure-Python project. Set it explicitly to restore cross-OS testing.

- `reusable-ci.yml` no longer passes `--ignore-missing-imports` to mypy; the project's own `[tool.mypy]` settings govern, and `typecheck-args` can relax them explicitly.

- `reusable-ci.yml` lints `src/ tests/` by default (`lint-paths`) and also runs `ruff format --check`, matching what a local `make qa` does.

- `reusable-ci.yml` cancels superseded runs on the same ref, except on the default branch.

- Third-party actions are pinned to commit SHAs rather than tags across all workflows, with the tag kept in a trailing comment.

- `skip-existing` is now explicit: TestPyPI keeps it on, PyPI defaults to off via `pypi-skip-existing`, because a silent no-op on the real index is indistinguishable from a successful release.

- Version headings now accept the inline-link form (`## [0.2.0](url) - DATE`) and the `[YANKED]` marker; both were previously unreadable, and `[YANKED]` corrupted the parsed version string into `0.2.0] - DATE [YANKED`. Exposed as `ChangelogEntry.link` and `ChangelogEntry.yanked`.

- A `##` heading that is not a version heading now ends the entry above it instead of silently extending it, and is recorded in `Changelog.unparsed_headings`. Headings before the first version heading remain preamble.

- `reusable-build-wheels.yml` no longer delegates to `reusable-collect-artifacts.yml` and `reusable-publish.yml`. Those calls named `@main` literally, so pinning the outer workflow to a tag still ran the publish step -- the one holding `id-token: write` -- from whatever `main` pointed at. Both remain available as standalone building blocks.

- `reusable-build-wheels.yml` collects artifacts by explicit name and pattern instead of downloading everything in the run, and fails if `dist/` contains anything other than `*.whl` and `*.tar.gz` or is empty.

- `automate changelog get` and `automate release-body` now emit the entry verbatim instead of re-rendering it from parsed sections. Tables, fenced code blocks, `*` bullets, and multi-word section headings are no longer silently dropped, and blank-line structure is preserved.

- A trailing block of link-reference definitions is excluded from the last entry's body.

### Fixed

- Code fences are tracked, so a `# ` or `## [x]` line inside a fenced example is content rather than structure. A changelog that documents its own format no longer acquires a bogus title, phantom entries, or lint errors from its examples.

- `automate` no longer duplicates its version string: `__version__` is read from installed package metadata, so a bump in `pyproject.toml` cannot drift from it.

- `src/automate/__main__.py` called `cli()` at import time. It is now guarded, so importing the module no longer runs the CLI.

- `reusable-release.yml` refuses to run on a non-tag ref instead of deriving a version from a branch name and failing later with a confusing message.

- `reusable-release.yml`: caller-supplied values (`project-description`, `changelog-path`, `automate-ref`, and the tag-derived version) reached bash through `${{ }}` interpolation inside `run:` bodies, where GitHub substitutes them textually before bash parses the script. A description containing a quote broke the release; one containing `$(...)` executed. All such values now arrive via step-level `env:`.

- `reusable-release.yml`: with `attach-artifacts: true` and an empty `dist/`, the literal string `dist/*` was passed to `gh release create`. The glob is now expanded under `nullglob` and the step fails with a clear message when no artifacts are present.

- `reusable-ci.yml`: `test-dir`, `test-extra-args`, `coverage-package`, `coverage-threshold`, and `src-dir` were interpolated into `run:` bodies, the same injection class as above. All now arrive via `env:`. `build-command` and `install-command` remain interpolated because they are shell commands by definition; this is now documented on both inputs.

- `reusable-ci.yml`: the test job never passed `matrix.python-version` to uv, so `uv sync` resolved an interpreter by its own discovery order -- a `.python-version` file wins outright -- and matrix cells could all run the same interpreter while reporting distinct labels. Each cell now pins `UV_PYTHON`.

### Removed

- `scripts/release_notes.py`. It duplicated `automate release-body`, matched version headings by exact string equality (so it found only undated headings and silently fell back to `[Unreleased]` otherwise), and disagreed with the CLI on the release-body heading text.

## [0.1.0] - 2026-03-31

### Added

- Keep a Changelog parser (`automate.changelog`) with `parse_changelog()`, `Changelog`, and `ChangelogEntry` types.

- CLI commands: `automate changelog get`, `automate changelog list`, `automate release-body`.

- Reusable GitHub Actions workflows: `reusable-ci.yml`, `reusable-build-wheels.yml`, `reusable-docs.yml`, `reusable-release.yml`.

- Composable workflow building blocks: `reusable-publish.yml` (trusted publishing to PyPI/TestPyPI) and `reusable-collect-artifacts.yml` (merge multiple artifacts).
