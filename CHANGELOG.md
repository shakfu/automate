# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-31

### Added

- Keep a Changelog parser (`automate.changelog`) with `parse_changelog()`, `Changelog`, and `ChangelogEntry` types.
- CLI commands: `automate changelog get`, `automate changelog list`, `automate release-body`.
- Reusable GitHub Actions workflows: `reusable-ci.yml`, `reusable-build-wheels.yml`, `reusable-docs.yml`, `reusable-release.yml`.
- Composable workflow building blocks: `reusable-publish.yml` (trusted publishing to PyPI/TestPyPI) and `reusable-collect-artifacts.yml` (merge multiple artifacts).
