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

Use `--format plain` to strip markdown bold markers.

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
reusable-ci.yml              test / lint / typecheck (independent)
reusable-docs.yml            mkdocs build + GitHub Pages deploy (independent)
reusable-release.yml         GitHub Release from tag + changelog (independent)

reusable-build-wheels.yml    cibuildwheel + collect + publish (convenience combo)
    |-- reusable-collect-artifacts.yml    merge multiple artifacts
    |-- reusable-publish.yml             trusted publishing to PyPI/TestPyPI
```

The top three are fully independent. `reusable-build-wheels.yml` is a convenience workflow that internally composes the collect and publish steps. For complex builds, use `reusable-collect-artifacts.yml` and `reusable-publish.yml` directly with your own build jobs.

---

## Guide: Simple Projects

A standard Python project with cibuildwheel, mkdocs, and PyPI publishing needs four thin wrapper workflows.

### Prerequisites

1. Configure [trusted publishing](https://docs.pypi.org/trusted-publishers/) on PyPI and TestPyPI for your repository.
2. Create GitHub environments named `pypi` and `testpypi` in your repository settings.
3. Set GitHub Pages source to "GitHub Actions" in your repository settings.

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

All inputs have sensible defaults. Override only what differs from your setup:

| Input | Default | Description |
|---|---|---|
| `python-versions` | `'["3.10","3.11","3.12","3.13","3.14"]'` | JSON array of Python versions |
| `os-matrix` | `'["ubuntu-latest","macos-latest","windows-latest"]'` | JSON array of OS labels |
| `coverage-threshold` | `80` | Minimum coverage percentage |
| `coverage-package` | *required* | Package name for `--cov` |
| `src-dir` | `src/` | Source directory for lint/typecheck |
| `test-dir` | `tests/` | Test directory |
| `test-extra-args` | `''` | Extra pytest arguments |
| `enable-lint` | `true` | Run `ruff check` |
| `enable-typecheck` | `true` | Run `mypy` |
| `enable-coverage` | `true` | Run coverage check |
| `build-command` | `''` | Custom build command (empty = just `uv sync`) |
| `install-command` | `''` | Custom install after build |

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

### Release process (simple project)

1. Update `CHANGELOG.md` with the new version entry.
2. Bump the version in `pyproject.toml`.
3. Commit and push to `main`.
4. Trigger the build-wheels workflow from the Actions tab. Select `pypi` as the publish target.
5. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`
6. The release workflow creates the GitHub Release automatically.

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

Version headers must match `## [VERSION]` or `## [VERSION] - YYYY-MM-DD`. Section headers must be one of: Added, Changed, Deprecated, Removed, Fixed, Security.

## Development

```bash
git clone https://github.com/shakfu/automate.git
cd automate
uv sync
make test       # run tests
make lint       # ruff check
make typecheck  # mypy
make qa         # all of the above
```

## License

MIT
