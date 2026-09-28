# LabMate knowledge base

The first implementation uses a local SQLite database with FTS5. It stores
page-bounded chunks and hard-filters by the manually selected device model.
This is the reliable lexical baseline for the later hybrid BM25 + embedding
retriever; it also preserves page and source-level evidence for the planner.

## Import a manual

From the project root:

```powershell
py -3.12 -m backend.knowledge.import_manual `
  'EPI-EWB204+ 使用(1).pdf' `
  --device-model 'EPI-EWB204+'
```

The output is `runtime/knowledge.db`. Re-run the command after replacing the
manual; the file hash prevents accidental duplicate documents.

## Retrieval contract

`retrieve.search(query, device_model)` returns page-bounded evidence with:

- document title;
- manually selected device model;
- PDF page number;
- section heading;
- source level.

The application uses the indexed result first and falls back to the old PDF
keyword scan only when the index has not been built. This makes the migration
safe while the knowledge base is being curated.
