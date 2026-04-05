# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [1.0.0] - 2026-04-02

### Added
- Declared typed-package support with `whire/py.typed`.
- Added a starter release changelog and repository ignore rules.

### Changed
- Marked the package metadata as production/stable.
- Tightened transaction list validation to require an integer limit between 1 and 100.
- Hardened `Retry-After` parsing to support both seconds and HTTP-date values.
- Normalized malformed payment-status payloads into `WhireError` with `invalid_response`.
- Marked `network_error` as retryable in the structured agent error surface.
