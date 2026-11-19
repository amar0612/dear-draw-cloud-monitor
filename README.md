# Dear Draw Cloud Monitor

## Historical recovery scope

The historical Nagaland Dear draw recovery window is **2024-06-01 through 2026-11-20 inclusive**.

- Include Nagaland Dear **1PM** and **8PM** draws only.
- Exclude Sikkim **6PM** and all other draw slots.
- Use `data/nagaland_master_prize_numbers.csv` as the candidate-date source for historical source discovery.
- Historical source discovery is batched (25 date/draw pairs by default). Set the workflow's `offset` and `limit` to continue through the filtered candidate list.
- Downloaded PDFs are archived with SHA-256 provenance. A downloaded PDF is **not** automatically human-verified; third-party mirror copies remain clearly labelled as such.
- The scheduled Sambad API workflow remains responsible for daily 1PM and 8PM imports.

The date window configures which candidate records are considered. It does not claim that every date in the window has been recovered or verified.
