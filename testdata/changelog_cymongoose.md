# CHANGELOG

All notable project-wide changes will be documented in this file. Note that each subproject has its own CHANGELOG.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Commons Changelog](https://common-changelog.org). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Types of Changes

- Added: for new features.
- Changed: for changes in existing functionality.
- Deprecated: for soon-to-be removed features.
- Removed: for now removed features.
- Fixed: for any bug fixes.
- Security: in case of vulnerabilities.

---

## [Unreleased]

## [0.2.0]

### Added

- **`serve_dir()` / `serve_file()` tests**: 11 tests in `tests/test_serve_static.py` covering text/binary/nested file serving, 404 handling, HTML Content-Type detection, extra headers, custom 404 pages, `serve_file` URI-independence, and nonexistent file handling.
- **MQTT pub/sub round-trip tests**: 6 tests in `tests/test_mqtt_pubsub.py` with a `MiniBroker` that sends CONNACK and routes published messages to subscribers.

### Fixed

- **`poll()` did not guard against concurrent calls**: Mongoose's event loop is single-threaded, but nothing prevented two threads from calling `Manager.poll()` simultaneously, which would corrupt internal data structures.

### Security

- **Header injection extended to `ws_upgrade()`**: The CR/LF/NUL header validation added to `reply()` in v0.1.14 was not applied to `Connection.ws_upgrade()`. Both methods now validate headers via a shared `_validate_header()` helper.

## [0.1.14]

### Changed

- **Network-dependent tests excluded by default**: Tests in `test_dns.py` and `test_sntp.py` are now marked with `@pytest.mark.network` and excluded from the default test run.
- **`AsyncManager` gains `shutdown_timeout` parameter**: Controls how long `__aexit__` waits for the poll thread to stop before abandoning it (default 30 seconds).

### Fixed

- **AsyncManager shutdown with large `poll_interval` and no connections**: `__aexit__` could raise `RuntimeError("Cannot close Manager while poll() is active")` when `poll_interval` exceeded the 2-second `join` timeout.

### Security

- **HTTP header injection in `Connection.reply()`**: Header names and values passed to `reply()` were concatenated verbatim without validation for control characters.
