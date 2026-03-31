# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Work-in-progress feature for async support.

## [0.3.0] - 2025-06-01

### Added

- New plugin system for extensibility.
- Support for YAML configuration files.

### Changed

- Migrated from `setup.py` to `pyproject.toml`.
- Improved error messages for invalid configuration.

### Deprecated

- The `--legacy-format` flag will be removed in v1.0.

## [0.2.0] - 2025-03-15

### Added

- Added `export` command for generating reports.

### Fixed

- Fixed memory leak in long-running processes.
- Corrected timezone handling in date parsing.

### Security

- Patched XSS vulnerability in HTML output.

## [0.1.0] - 2025-01-01

### Added

- Initial release.
- Basic CLI with `init` and `run` commands.
