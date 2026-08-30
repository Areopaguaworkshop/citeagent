# Changelog

All notable public changes to CiteAgent are recorded here. Release notes must
not include private corpus data, local paths, session content, or credentials.

## Unreleased

### Added

- Local, metadata-only paper workspaces with approved-source scoping.
- Checkpointed research workflow with `proceed`, `refine`, and `abort` states.
- Compact opt-in research-session state, operational `status`, and `doctor`.
- Structured tool errors with an error code and suggested next action.
- CI coverage for TypeScript checks, package inspection, and the Python harness.
- Public data-boundary policy in `PRIVACY.md`.

### Changed

- Corpus searches now honour the active paper's approved source IDs.
- The public MCP surface grows from 29 to 41 tools; two ingestion tools remain
  optional `citeindex` integrations.

### Fixed

- Workflow startup now fails closed when scoped retrieval produces no evidence.
- Local workflow, session, and paper metadata are excluded from source control.
