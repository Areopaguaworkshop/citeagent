# CiteAgent data boundary

CiteAgent is distributed without a corpus, library, paper workspace, local
state, session memory, logs, model files, credentials, or source-derived
outputs. These stay on the user's machine.

The optional `CITEAGENT_STATE_ROOT` directory contains user-created paper
metadata, workflow checkpoints, and opt-in session metadata. It is ignored by
Git and must not be included in a release artifact.

For reproducible public examples, use invented metadata and synthetic source
text only. Do not contribute real research documents, notes, bibliographies,
glossaries, or local paths unless they are explicitly cleared for publication.
