# Dear Draw Cloud Monitor

## Historical recovery scope

The historical Nagaland Dear draw recovery window is **2024-06-01 through 2026-11-20 inclusive**.

- Include Nagaland Dear **1PM** and **8PM** draws only.
- Exclude Sikkim **6PM** and all other draw slots.
- Use `data/nagaland_master_prize_numbers.csv` as the candidate-date source for historical source discovery.
- Historical source discovery is batched (25 date/draw pairs by default). Set the workflow's `offset` and `limit` to continue through the filtered candidate list.
- Downloaded PDFs are archived with SHA-256 provenance. A downloaded PDF is **not** automatically human-verified; third-party mirror copies remain clearly labelled as such.
- The scheduled Sambad API workflow remains responsible for daily 1PM and 8PM imports.

## Source registry

`data/nagaland_source_registry.csv` is the complete 25-entry source registry recovered during source research. It preserves every supplied source URL or URL pattern, source class, draw scope, coverage note, and ingestion status.

- Entries 0–22 are source portals, APIs, archive roots, date routes, mirrors, or reference charts to investigate for 1PM/8PM evidence.
- Entries 23–24 are intentionally retained as **EXCLUDE / DISCREPANCY** records. They must not be treated as valid Nagaland 1PM/8PM sources unless their draw schedules are independently confirmed.
- Several entries are archive landing pages or dynamic calendars, not direct PDF endpoints. Their inclusion in the registry means they are retained as discovery leads; it does **not** mean the current PDF downloader has implemented a date-specific extractor for every one of the 25 entries.
- Do not silently drop a source because it disagrees with another source. Preserve each retrieved copy and its provenance, then flag identical hashes or content conflicts for comparison.

The date window configures which candidate records are considered. It does not claim that every date in the window has been recovered or verified.
