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

- The recovery engine reads the registry at runtime. It attempts the 21 applicable result-source entries for each requested date/draw, including official PDF patterns, annual calendars, archive landing pages, date-specific routes, and the legacy mirror.
- Entries 23–24 remain **EXCLUDE / DISCREPANCY** and are never queried as Nagaland 1PM/8PM sources without independent schedule confirmation.
- Entry 3 is API documentation (not a result endpoint and requires credentials); entry 21 is a first-prize-only reference chart. Neither is treated as a full 132-prize PDF source.
- For HTML archive roots, the engine follows date-specific links and year/month archive links, then checks linked pages for PDFs. Site-specific JavaScript-only selectors or undocumented APIs may still require a dedicated adapter; an attempted source is not proof that its archive was exhaustively crawled.
- Every successful PDF is stored separately under `sources/historical/copies/` with a source-specific filename and SHA-256 hash. The manifest retains the source URL, discovery URL, file path, hash, byte count, and comparison status.
- Identical hashes are grouped; differing hashes for the same date/draw are flagged as `source_content_conflict`. Conflicting copies are retained, never silently overwritten or discarded.
- Source retrieval is not number verification. All copies remain pending number-by-number comparison; no source is automatically marked human-verified.

The date window configures which candidate records are considered. It does not claim that every date in the window has been recovered or verified.

## Automatic cloud-to-app synchronization

The scheduled API workflow fetches Nagaland Dear 1PM and 8PM results, validates all 132 prize entries, and writes accepted records to Supabase. The app now also reads the authenticated user's cloud draw rows:

- Fetches cloud rows after the app loads and the user is signed in.
- Pages through the cloud table in batches of 1,000 rows.
- Accepts only complete 1PM/8PM rows with the expected prize-tier counts and number formats.
- Merges by draw date and slot; identical local rows are left alone.
- Replaces a matching sample row with a validated cloud row.
- Preserves a differing non-sample local row and reports the conflict rather than overwriting it.
- Refreshes every five minutes and when the app becomes visible again.

### Required one-time Supabase setup

Apply `supabase/migrations/20261120_authenticated_draws_read.sql` in the Supabase SQL Editor for project `sxdrqithncjdrokwpkzm`. This grants authenticated users read access to Nagaland 1PM/8PM draw rows only. Until this migration is applied, the app's cloud read will fail with a permissions/RLS error; local history remains available.

The GitHub Actions secrets `LOTTERY_SAMBAD_API_TOKEN` and `SUPABASE_SECRET_KEY` must also be configured for scheduled API fetching and cloud writes. Secret values must never be placed in browser code.
