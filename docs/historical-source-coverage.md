# Nagaland historical source coverage investigation

Research snapshot: 18 November 2026

Scope: Nagaland 1 PM and 8 PM only. Sikkim 6 PM is excluded.

## Findings

### 1. Government of Nagaland result portal

- The Directorate's current result-gazette page is `https://www.nagalandlotteries.com/results.php`.
- Its indexed page currently exposes calendar entries for September, October and November 2026; this page view does not establish older-year coverage.
- A government-hosted PDF was independently located at `/old_results/MN020226.PDF` (2 February 2026, 1 PM). Its document header identifies the Directorate of State Lotteries, Nagaland, Kohima.
- Another government-hosted 2025 PDF was located at `/old_results/MN151025.PDF`.
- Independent archive documentation reports that the official `old_results` PDF archive is available from September 2025 onward. Treat this as a useful coverage lead, not proof that no earlier government PDFs exist.
- Direct tests of the guessed government URLs `MN310123.PDF` and `EN100123.PDF` did not retrieve the January 2023 files. A failed guessed URL is not proof that the result never existed.

### 2. January 2023 mirror copies retrieved

Two PDFs were successfully downloaded from a third-party mirror. They are retained as secondary evidence only:

| Draw | Filename | Mirror URL | SHA-256 |
|---|---|---|---|
| 2023-01-10 8PM | ED100123.pdf | `https://lotterysambadresult.in/wp-content/uploads/2023/01/ED100123.pdf` | `2c62b83c8daf444e31fec5406c1fcbde8184b1f8880fb96c7c87d085de2df886` |
| 2023-01-31 1PM | MD310123.pdf | `https://lotterysambadresult.in/wp-content/uploads/2023/01/MD310123.pdf` | `cf235502972f73f56758ad646d59aceef5b1848331f584747bb3ea8ab9fd379c` |

The filenames `MDDDMMYY.pdf` (1PM) and `EDDDMMYY.pdf` (8PM) are a legacy mirror naming convention observed for these two records. They must not be assumed to be the government server's naming convention.

### 3. Other discovery leads

- `https://www.lotterysambad.com/old-result.php` exposes date selectors for 1PM, 6PM and 8PM, but its date selector is dynamic and the text index alone does not expose the underlying historical PDF URLs.
- `https://www.nagalandstatelotteries.in/oldresult.htm` has a different set of draw slots (12:00, 4:00, 4:30 and 8:00) and is not a safe substitute for the Nagaland 1PM/8PM archive.
- Independent sites claim broader historical coverage (some state 2021 onward, others Jan 2022 onward). Treat these as discovery indexes only; every PDF must be downloaded, fingerprinted and compared before use.

## Safe ingestion rules

1. Enumerate candidate dates from the existing CSV; do not fabricate missing draw dates.
2. Restrict slots to 1PM and 8PM.
3. Try the government PDF candidate first using `MNDDMMYY.PDF` or `ENDDMMYY.PDF`.
4. Try legacy mirror candidates only after the government URL fails.
5. Record exact URL, source class, byte count and SHA-256.
6. Never label a third-party mirror as an official government file.
7. Never promote a PDF or its numbers to `human_verified` automatically.
8. Keep failed lookups in the manifest so gaps are measurable.
9. Process small batches to avoid hammering sources and to make failures reviewable.

## Current conclusion

The investigation confirms a usable official government PDF endpoint for at least some 2025/2026 dates, and usable third-party mirror copies for the two human-verified January 2023 examples. It does **not** yet establish complete official PDF coverage for 2021–2024 or all of 2025–2026.
