# automate

Reusable GitHub Actions workflows and a local CLI helper for automating Python project releases.

Provides composable building blocks for CI, wheel building, documentation deployment, PyPI publishing, and GitHub Release creation. Designed so that simple projects can adopt the full stack with minimal configuration, while complex projects (GPU backends, custom build systems) can swap in their own build step and still use the shared pieces.

## Installation

```bash
pip install "git+https://github.com/shakfu/automate.git"
```

Or run without installing:

```bash
uvx --from "git+https://github.com/shakfu/automate.git" automate --help
```

## CLI Usage

### List changelog versions

```bash
automate changelog list -f CHANGELOG.md
```

```
Unreleased
0.2.0  2025-06-01
0.1.0  2025-01-01
```

### Extract a changelog entry

```bash
automate changelog get 0.2.0 -f CHANGELOG.md
```

```markdown
### Added

- New plugin system for extensibility.

### Fixed

- Fixed memory leak in long-running processes.
```

Use `--format plain` to strip markdown bold markers (`**`). Other markup is left intact.

### Lint a changelog

```bash
automate changelog lint -f CHANGELOG.md
```

```
CHANGELOG.md:9: error: unknown-section: 'Security Fixes' is not one of Added, Changed, Deprecated, Fixed, Removed, Security; its items are dropped from the structured view
CHANGELOG.md:15: error: non-dash-bullet: list items must start with '- '; this one is dropped from the structured view
2 error(s), 0 warning(s)
```

Reports content the parser would drop or misattribute. Exits non-zero on errors, so a release workflow can gate on it; `--strict` also fails on warnings. Codes:

| Code | Severity | Meaning |
|---|---|---|
| `unparsed-heading` | error | A `##` heading that is not a version heading; content below it belongs to no entry |
| `unknown-section` | error | A `### Section` outside the Keep a Changelog set; its items vanish from the structured view |
| `non-dash-bullet` | error | A `*` or `+` list item; dropped from the structured view |
| `orphan-content` | error | Content under a version heading but outside any section |
| `duplicate-version` | error | Two entries share a version; lookups return the first |
| `non-list-content` | warning | Non-list content inside a section: kept verbatim, absent from the structured view |
| `missing-date` | warning | A released version with no date |
| `empty-section` | warning | A section heading with no items |

Content inside fenced code blocks is ignored, so a changelog that documents the format does not fail its own lint.

### Cut a release entry

```bash
automate changelog release 0.3.0
```

```
CHANGELOG.md: released 0.3.0 (2026-08-26)
```

Stamps the accumulated `[Unreleased]` content as a dated release:

```diff
 ## [Unreleased]

+## [0.3.0] - 2026-08-26
+
 ### Added

 - New plugin system for extensibility.
```

The heading is inserted above the existing body rather than the body being re-rendered, so tables, fenced code, and bullet styles the parser does not model survive byte for byte. `[Unreleased]` stays in place, empty, ready for the next cycle.

A date is always written, which is the reason to use this instead of editing by hand: the undated heading `changelog lint` warns about and `check-release` rejects cannot be produced here. The command refuses to run when the version already exists, when there is no `[Unreleased]` heading, or when `[Unreleased]` is empty.

`--date YYYY-MM-DD` overrides today's date; `--dry-run` prints the result instead of writing it. If `pyproject.toml` declares a different version, or the file still carries an `[Unreleased]: <url>` link definition pointing at the previous release, the command says so on stderr without failing -- both need a human decision.

### Check that a version is publishable

```bash
automate check-release 0.3.0
```

```
CHANGELOG.md: 0.3.0 is ready to release
```

Verifies one specific version, and is deliberately stricter than `changelog lint`: the entry must exist, carry a date, and have content, and `pyproject.toml` must declare the same version. Exits non-zero listing every problem found.

| Code | Meaning |
|---|---|
| `changelog-lint` | An error-severity `changelog lint` issue anywhere in the file |
| `version-missing` | No entry for the version being released |
| `version-unreleased` | The version resolves to the in-progress `[Unreleased]` entry |
| `missing-date` | The entry has no release date |
| `empty-entry` | The entry has no content, so the release body would be empty |
| `version-mismatch` | `pyproject.toml` declares a different version |

`missing-date` is a warning in `changelog lint`, which has to serve any changelog, and a hard failure here, where the entry is about to become a permanent release record. The packaging check is skipped when `pyproject.toml` is absent or declares a dynamic version; `--pyproject PATH` points at a different file and `--no-pyproject` skips it entirely.

### Generate a GitHub Release body

```bash
automate release-body 0.2.0 -f CHANGELOG.md -d "A Python library for doing things."
```

```markdown
A Python library for doing things.

## Changes since the last release

### Added

- New plugin system for extensibility.

### Fixed

- Fixed memory leak in long-running processes.
```

## Reusable Workflows

All workflows are called via `uses: shakfu/automate/.github/workflows/<name>@main`.

### Architecture

The workflows are designed as independent, composable pieces:

```
reusable-ci.yml              test / lint / typecheck
reusable-docs.yml            mkdocs build + GitHub Pages deploy
reusable-release.yml         GitHub Release from tag + changelog
reusable-build-wheels.yml    cibuildwheel + collect + publish (self-contained)

reusable-collect-artifacts.yml    merge multiple artifacts   } building blocks for
reusable-publish.yml              trusted publishing         } your own build jobs
```

Every workflow is independent and makes no nested `uses:` calls, so pinning one to a tag or SHA pins everything it runs. `reusable-build-wheels.yml` covers the common case end to end; for complex builds, use `reusable-collect-artifacts.yml` and `reusable-publish.yml` directly with your own build jobs.

---

## Guide: Simple Projects

A standard Python project with cibuildwheel, mkdocs, and PyPI publishing needs four thin wrapper workflows.

### Prerequisites

1. Configure [trusted publishing](https://docs.pypi.org/trusted-publishers/) on PyPI and TestPyPI for your repository.

2. Create GitHub environments named `pypi` and `testpypi` in your repository settings.

3. Add a required reviewer to the `pypi` environment. Nothing in these workflows gates the step between building and publishing; the environment approval is that gate, and it is a repository setting.

4. Set GitHub Pages source to "GitHub Actions" in your repository settings.

### CI (test, lint, typecheck)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    uses: shakfu/automate/.github/workflows/reusable-ci.yml@main
    with:
      coverage-package: mypackage
```

For C extension projects that need a build step before testing:

```yaml
jobs:
  ci:
    uses: shakfu/automate/.github/workflows/reusable-ci.yml@main
    with:
      coverage-package: mypackage
      build-command: "uv build --wheel"
      install-command: "uv pip install dist/*.whl"
      test-extra-args: "--ignore=tests/examples"
```

Each matrix cell pins its interpreter with `UV_PYTHON`, so the reported Python version is the one actually tested. Set `python-versions` to a subset of your project's `requires-python`; an entry outside that range fails the sync step rather than quietly testing a different interpreter.

All inputs have sensible defaults. Override only what differs from your setup:

| Input | Default | Description |
|---|---|---|
| `python-versions` | `'["3.10","3.11","3.12","3.13","3.14"]'` | JSON array of Python versions. Must be a subset of your `requires-python` |
| `os-matrix` | `'["ubuntu-latest"]'` | JSON array of OS labels. Linux only by default: the matrix is a cross product |
| `coverage-threshold` | `80` | Minimum coverage percentage |
| `coverage-package` | *required* | Package name for `--cov` |
| `src-dir` | `src/` | Source directory for the type checker |
| `lint-paths` | `src/ tests/` | Space-separated paths to lint and format-check |
| `test-dir` | `tests/` | Test directory |
| `test-extra-args` | `''` | Extra pytest arguments |
| `typecheck-args` | `''` | Extra mypy arguments; empty so your `[tool.mypy]` governs |
| `tool-python-version` | `'3.13'` | Python for the lint and type-check jobs |
| `enable-lint` | `true` | Run `ruff check` and `ruff format --check` |
| `enable-typecheck` | `true` | Run `mypy` |
| `enable-coverage` | `true` | Collect coverage and enforce the threshold, inside the test job |
| `build-command` | `''` | Custom build command (empty = just `uv sync`) |
| `install-command` | `''` | Custom install after build |

Three jobs run: `test` (matrix), `lint`, and `type-check`. Coverage is collected inside the test job rather than in a job of its own, which would re-run the whole suite and any custom build with it.

Superseded runs on the same ref are cancelled, except on the default branch.

### Build wheels and publish

```yaml
# .github/workflows/build-wheels.yml
name: Build Wheels

on:
  workflow_dispatch:
    inputs:
      publish-target:
        type: choice
        options: [none, testpypi, pypi, both]
        default: none

permissions:
  id-token: write
  contents: read

jobs:
  build:
    uses: shakfu/automate/.github/workflows/reusable-build-wheels.yml@main
    with:
      package-name: mypackage
      publish-target: ${{ inputs.publish-target }}
      cibw-environment-linux: "CFLAGS='-O3 -std=c99'"
      cibw-environment-macos: "CFLAGS='-O3 -std=c99'"
      cibw-test-skip: "*-win*"
```

| Input | Default | Description |
|---|---|---|
| `package-name` | *required* | PyPI package name |
| `publish-target` | `none` | `none`, `testpypi`, `pypi`, or `both` |
| `os-matrix` | `'["ubuntu-latest","windows-latest","macos-14"]'` | Build runners |
| `cibw-build` | `'cp310-* cp311-* cp312-* cp313-* cp314-*'` | Python versions to build |
| `cibw-skip` | `'*-win32 *-manylinux_i686 *-musllinux_* *-win_arm64'` | Platforms to skip |
| `cibw-archs-linux` | `'x86_64 aarch64'` | Linux architectures |
| `cibw-archs-macos` | `'x86_64 arm64'` | macOS architectures |
| `cibw-archs-windows` | `AMD64` | Windows architectures |
| `cibw-environment-linux` | `''` | Linux build environment |
| `cibw-environment-macos` | `''` | macOS build environment |
| `cibw-test-requires` | `'pytest>=8'` | Test dependencies |
| `cibw-test-command` | `'pytest {project}/tests -v'` | Test command |
| `cibw-test-skip` | `''` | Platforms to skip testing |
| `pypi-skip-existing` | `false` | Treat an already-published version as success. Off by default: a silent no-op looks like a successful release |

### Documentation

```yaml
# .github/workflows/docs.yml
name: Docs

on:
  push:
    branches: [main]
    paths: [docs/**, mkdocs.yml, .github/workflows/docs.yml]
  workflow_dispatch:

permissions:
  pages: write
  id-token: write

jobs:
  docs:
    uses: shakfu/automate/.github/workflows/reusable-docs.yml@main
```

| Input | Default | Description |
|---|---|---|
| `python-version` | `'3.12'` | Python version |
| `build-command` | `'uv run mkdocs build --strict'` | Docs build command |
| `site-dir` | `site/` | Build output directory |

Note: some projects deploy docs via `make docs-deploy` instead of a GitHub Actions workflow. The reusable workflow is optional.

### GitHub Releases

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  release:
    uses: shakfu/automate/.github/workflows/reusable-release.yml@main
    with:
      project-description: "Python bindings for the Mongoose embedded networking library."
      attach-artifacts: true
```

This creates a GitHub Release when you push a tag. The release body includes the project description and the matching CHANGELOG.md entry. Set `attach-artifacts: true` to download and attach wheel artifacts from a prior build workflow run.

| Input | Default | Description |
|---|---|---|
| `project-description` | `''` | Project description paragraph |
| `changelog-path` | `CHANGELOG.md` | Path to changelog |
| `attach-artifacts` | `false` | Attach wheel artifacts |
| `artifact-name` | `all-dist` | Artifact name to download |
| `automate-ref` | `main` | Git ref of automate to install |
| `lint-changelog` | `true` | Run `automate changelog lint` and fail on errors before generating the body |
| `verify-release` | `true` | Run `automate check-release` on the tagged version before generating the body |
| `pyproject-path` | `pyproject.toml` | Packaging metadata `check-release` cross-checks the tag against |

The workflow refuses to run on anything but a tag push, rather than deriving a version from a branch name and failing later with a confusing message.

`verify-release` is the gate that stops a bad release from being published rather than reporting it afterwards: a tag whose version has no changelog entry, no date, no content, or a version `pyproject.toml` disagrees with fails before `gh release create` runs. Set it to `false` only if your version lives somewhere the check cannot read.

### Release process (simple project)

1. Bump the version in `pyproject.toml`.

2. Stamp the changelog: `automate changelog release 0.2.0`. This moves the accumulated `[Unreleased]` content under a dated `## [0.2.0]` heading.

3. Verify: `automate check-release 0.2.0`. This is the same check the release workflow runs, so a failure here is a failure you would otherwise have discovered after tagging.

4. Commit and push to `main`. Keep the version bump and the changelog stamp in one commit -- they are one change, and splitting them leaves `main` in a state that fails its own release check.

5. Trigger the build-wheels workflow from the Actions tab. Select `pypi` as the publish target.

6. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`

7. The release workflow re-runs `check-release` against the tag and creates the GitHub Release automatically.

Steps 1 through 3 are `make release` and `make check-release` in this repository, which default `VERSION` to whatever `pyproject.toml` declares.

---

## Guide: Complex Projects

Projects with bespoke build requirements (GPU backends, custom build orchestrators, multi-backend wheel variants) should keep their own build workflow and use the composable pieces for everything else.

### The principle

Replace `reusable-build-wheels.yml` with your own build jobs. Use `reusable-collect-artifacts.yml` and `reusable-publish.yml` for the artifact collection and publishing steps that are identical regardless of how wheels were built. The CI, docs, and release workflows work unchanged.

### Composable building blocks

**`reusable-collect-artifacts.yml`** -- merges multiple upload artifacts into one:

| Input | Default | Description |
|---|---|---|
| `pattern` | `''` | Glob pattern for artifact names (e.g. `"wheels-*"`) |
| `output-name` | `all-dist` | Merged artifact name |
| `retention-days` | `30` | Retention period |

**`reusable-publish.yml`** -- publishes to PyPI or TestPyPI via trusted publishing:

| Input | Default | Description |
|---|---|---|
| `package-name` | *required* | PyPI package name |
| `target` | *required* | `testpypi` or `pypi` |
| `artifact-name` | `all-dist` | Artifact to publish |
| `skip-existing` | `false` | Treat an already-published version as success |

Required permissions in the calling workflow:

```yaml
permissions:
  id-token: write
```

### Example: GPU wheel project

A project that builds CUDA and ROCm wheel variants with a custom build system:

```yaml
# .github/workflows/build-gpu-wheels.yml
name: Build GPU Wheels

on:
  workflow_dispatch:
    inputs:
      publish-target:
        type: choice
        options: [none, testpypi, pypi]
        default: none

permissions:
  id-token: write
  contents: read

jobs:
  cuda:
    name: Build CUDA wheels
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # ... custom CUDA toolchain setup ...
      # ... custom build steps ...

      - uses: actions/upload-artifact@v4
        with:
          name: wheels-cuda
          path: dist/*.whl

  rocm:
    name: Build ROCm wheels
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # ... custom ROCm toolchain setup ...
      # ... custom build steps ...

      - uses: actions/upload-artifact@v4
        with:
          name: wheels-rocm
          path: dist/*.whl

  collect:
    needs: [cuda, rocm]
    uses: shakfu/automate/.github/workflows/reusable-collect-artifacts.yml@main
    with:
      pattern: "wheels-*"
      output-name: all-dist

  publish:
    if: inputs.publish-target != 'none'
    needs: [collect]
    uses: shakfu/automate/.github/workflows/reusable-publish.yml@main
    with:
      package-name: mypackage
      target: ${{ inputs.publish-target }}
      artifact-name: all-dist
```

The CI, docs, and release workflows are configured the same way as for simple projects:

```yaml
# .github/workflows/ci.yml -- same as simple project
jobs:
  ci:
    uses: shakfu/automate/.github/workflows/reusable-ci.yml@main
    with:
      coverage-package: mypackage
      build-command: "python scripts/manage.py build"
      install-command: "pip install dist/*.whl"

# .github/workflows/release.yml -- same as simple project
on:
  push:
    tags: ['v*']
jobs:
  release:
    uses: shakfu/automate/.github/workflows/reusable-release.yml@main
    with:
      project-description: "Python bindings for llama.cpp with GPU acceleration."
      attach-artifacts: true
```

### What stays shared vs. what you own

| Component | Simple project | Complex project |
|---|---|---|
| CI (test/lint/typecheck) | `reusable-ci.yml` | `reusable-ci.yml` |
| Wheel building | `reusable-build-wheels.yml` | **Your own workflow** |
| Artifact collection | (included in build-wheels) | `reusable-collect-artifacts.yml` |
| Publishing | (included in build-wheels) | `reusable-publish.yml` |
| Docs | `reusable-docs.yml` | `reusable-docs.yml` |
| GitHub Releases | `reusable-release.yml` | `reusable-release.yml` |
| Changelog parsing | `automate` CLI | `automate` CLI |

## CHANGELOG Format

The CLI expects [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format:

```markdown
# Changelog

## [Unreleased]

## [0.2.0] - 2025-06-01

### Added

- New feature description.

### Fixed

- Bug fix description.
```

Version headers must match one of:

```markdown
## [Unreleased]
## [0.2.0]
## [0.2.0] - 2025-06-01
## [0.2.0](https://github.com/owner/repo/releases/tag/v0.2.0) - 2025-06-01
## [0.2.0] - 2025-06-01 [YANKED]
```

Any other `##` heading after the first version heading ends the entry above it rather than being absorbed into it, and is reported in `Changelog.unparsed_headings` so a release can be failed on it. Headings before the first version heading are preamble.

`automate changelog get` and `automate release-body` reproduce the entry verbatim from the source file, so tables, fenced code blocks, `*` bullets, and section headings outside the conventional set are preserved as written. A trailing block of link-reference definitions (`[1.0.0]: https://...`) is treated as belonging to the document rather than to the last entry, and is excluded.

The structured view exposed by the `automate.changelog` API (`ChangelogEntry.sections`) is narrower: it records only `### Section` headings of a single word and `- ` bullets. Use `ChangelogEntry.raw` when the goal is to reproduce the source.

## Supply chain

Third-party actions are pinned to commit SHAs rather than tags, with the tag kept in a trailing comment. A tag is a moving pointer its owner can repoint; these workflows hold `contents: write` and `id-token: write`, so the ref they run is part of the release supply chain. `.github/dependabot.yml` keeps the pins current, and `tests/test_workflows.py` fails if an unpinned action appears.

No workflow makes a nested cross-repo `uses:` call, so pinning one of these workflows to a tag or SHA pins everything it runs.

## Development

```bash
git clone https://github.com/shakfu/automate.git
cd automate
uv sync
make test       # run tests
make lint       # ruff check
make format-check  # ruff format --check
make typecheck  # mypy
make qa         # all of the above

make release        # stamp [Unreleased] as VERSION (default: pyproject's version)
make check-release  # verify VERSION is publishable
```

Workflow changes are checked by [actionlint](https://github.com/rhysd/actionlint) in CI and by `tests/test_workflows.py`, which asserts no caller-supplied value is interpolated into a `run:` body, no cross-repo nested workflow calls exist, and every action is SHA-pinned.

The test suite dogfoods the CLI against this repository: `CHANGELOG.md` must pass `changelog lint --strict`, and the version in `pyproject.toml` must pass `check-release`. Both fail in CI if a release is cut by hand and the metadata is left inconsistent.

## License

MIT
