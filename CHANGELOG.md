# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet — Phase 1 (integration scaffold) is next.

## [0.0.1] — 2026-05-26

### Added (Phase 0 — architecture)

- Repository scaffolded with public-quality layout: `LICENSE` (Apache 2.0),
  `README.md`, `CHANGELOG.md`, `info.md`, `hacs.json`, `.gitignore`
- `docs/architecture.md` capturing:
  - Cloud API surface (single documented endpoint;
    `https://api.visiblair.com:11000/api/v1/sensor?uuid=<MAC>&viewToken=<TOKEN>`)
  - Authentication model (per-device viewToken, no account-level API key)
  - The "open catch-all" trap (every unknown route returns `200 OK` with
    `Content-Length: 0` — defensive parsing required)
  - Local API documented but non-viable (firmware 1.7.2 disconnect bug)
  - Entity map: which payload fields become which HA entity types
  - Defensive parsing rules
  - Coordinator + polling design
  - Config-flow model (one entry per sensor)
- `tests/fixtures/sensor_response.json` — captured real-world response
  with credentials redacted, for use in unit tests
