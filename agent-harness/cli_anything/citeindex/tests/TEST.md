# TEST.md — cli-anything-citeindex

## Test Inventory Plan

- `test_core.py`: ~16 unit tests
- `test_full_e2e.py`: ~15 E2E tests (intermediate + true backend + subprocess)

## Unit Test Plan

### Module: `utils/citeindex_backend.py`
- `CiteIndexBackend` importable (1)
- Backend has required methods: ingest, search, chat, memory_search, memory_list_threads, format_bibliography (1)
- `check_dependencies` returns correct structure (1)

### Module: `utils/output.py`
- JSON mode output (1)
- Human mode dict output (1)
- Human mode error output (1)
- Human mode list output (1)
- Human mode string output (1)

### Module: `core/session.py`
- Session create (1)
- Session save/load cycle (1)
- Undo/redo stack push/pop (1)
- Session to/from dict serialization (1)
- Session list (1)
- Session delete (1)

### Module: `core/project.py`
- project_new creates directory (1)
- project_info on empty corpus (1)
- project_info on nonexistent path (1)
- project_validate on empty corpus (1)
- project_list on empty dir (1)

### Module: `core/ingest.py`
- Module importable (1)
- _build_ingest_config builds correct dict (1)

### Other modules (importability)
- core/search, core/chat, core/memory, core/export (4)

## E2E Test Plan

### Intermediate tests
- Session JSON round-trip produces valid JSON
- `--json` flag produces valid JSON with expected schema
- Corpus folder creation after `project new`
- Export render produces non-empty text file (graceful error on empty corpus)

### True backend tests
- Ingest a real PDF → verify corpus files created
- Search after ingest → BM25 results returned
- Chat after ingest → trace-bound citations in response
- Export render → output file exists and has content
- Memory round-trip

### CLI subprocess tests
- `--help` works
- `--json` flag works with project new
- Full workflow: project new → info → validate

## Realistic Workflow Scenarios

### Workflow 1: Research paper ingestion pipeline
- **Simulates:** Scholar ingesting a PDF into their research corpus
- **Operations:** project new → ingest file → project info → search query
- **Verified:** Corpus created, document files exist, search returns results

### Workflow 2: Citation export
- **Simulates:** Exporting a bibliography from ingested sources
- **Operations:** (assumes corpus exists) export render → verify output
- **Verified:** Output file exists, non-empty, contains formatted citations

### Workflow 3: Interactive session with undo
- **Simulates:** Researcher working in REPL with undo capability
- **Operations:** session create → ingest → session undo → session redo
- **Verified:** Undo clears action, redo restores it

## Test Results

```
$ CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest cli_anything/citeindex/tests/ -v -s

============================= test session starts =============================
platform linux -- Python 3.12.8, pytest-9.0.2, pluggy-1.6.0
collected 44 items

test_core.py::TestCiteIndexBackend::test_import_backend_module PASSED
test_core.py::TestCiteIndexBackend::test_backend_has_required_methods PASSED
test_core.py::TestCiteIndexBackend::test_check_dependencies PASSED
test_core.py::TestOutputFormat::test_format_output_json_mode PASSED
test_core.py::TestOutputFormat::test_format_output_human_dict PASSED
test_core.py::TestOutputFormat::test_format_output_human_error PASSED
test_core.py::TestOutputFormat::test_format_output_human_list PASSED
test_core.py::TestOutputFormat::test_format_output_human_string PASSED
test_core.py::TestSession::test_session_create PASSED
test_core.py::TestSession::test_session_save_load PASSED
test_core.py::TestSession::test_session_undo_redo_stack PASSED
test_core.py::TestSession::test_session_to_from_dict PASSED
test_core.py::TestSession::test_session_list PASSED
test_core.py::TestSession::test_session_delete PASSED
test_core.py::TestProjectModule::test_project_new_creates_corpus_dir PASSED
test_core.py::TestProjectModule::test_project_info_empty_corpus PASSED
test_core.py::TestProjectModule::test_project_info_nonexistent PASSED
test_core.py::TestProjectModule::test_project_validate_empty PASSED
test_core.py::TestProjectModule::test_project_list_empty_dir PASSED
test_core.py::TestIngestModule::test_ingest_module_importable PASSED
test_core.py::TestIngestModule::test_ingest_file_builds_config PASSED
test_core.py::TestSearchModule::test_search_module_importable PASSED
test_core.py::TestChatModule::test_chat_module_importable PASSED
test_core.py::TestMemoryModule::test_memory_module_importable PASSED
test_core.py::TestExportModule::test_export_module_importable PASSED
test_core.py::TestCLIEntryPoint::test_cli_module_importable PASSED
test_core.py::TestCLIEntryPoint::test_cli_has_command_groups PASSED
test_full_e2e.py::TestSessionE2E::test_session_json_valid PASSED
test_full_e2e.py::TestSessionE2E::test_session_json_has_required_fields PASSED
test_full_e2e.py::TestProjectE2E::test_project_new_creates_citeindex_dir PASSED
test_full_e2e.py::TestProjectE2E::test_project_info_after_new PASSED
test_full_e2e.py::TestProjectE2E::test_export_render_produces_file PASSED
test_full_e2e.py::TestCLISubprocess::test_help PASSED
test_full_e2e.py::TestCLISubprocess::test_version PASSED
test_full_e2e.py::TestCLISubprocess::test_project_help PASSED
test_full_e2e.py::TestCLISubprocess::test_ingest_help PASSED
test_full_e2e.py::TestCLISubprocess::test_search_help PASSED
test_full_e2e.py::TestCLISubprocess::test_chat_help PASSED
test_full_e2e.py::TestCLISubprocess::test_memory_help PASSED
test_full_e2e.py::TestCLISubprocess::test_export_help PASSED
test_full_e2e.py::TestCLISubprocess::test_session_help PASSED
test_full_e2e.py::TestCLISubprocess::test_project_new_json PASSED
test_full_e2e.py::TestCLISubprocess::test_project_info_json PASSED
test_full_e2e.py::TestCLISubprocess::test_project_validate_json PASSED

========================= 44 passed in 1.17s =========================
```

## Summary Statistics

- **Total tests:** 44
- **Pass rate:** 100%
- **Execution time:** 1.17s
- **Unit tests:** 27
- **E2E tests:** 17

## Coverage Notes

- Backend methods (ingest, search, chat, memory) are tested for importability only —
  real PDF/URL ingestion requires system dependencies (tesseract, ffmpeg, ollama)
- Subprocess tests verify `cli-anything-citeindex` --help, --version, --json, and
  project commands work against the installed binary
- No true-backend E2E tests yet (requires real PDF + ollama running)
- REPL is tested indirectly (invoke_without_command=True dispatches to repl)