# Project working rules

1. Preserve the original CSV files in `data/raw/`.
2. Never silently discard or impute records.
3. Validate identifiers and lookup joins before calculating results.
4. Keep notebook analysis reproducible from the Python pipeline.
5. Use the chronological model holdout in weeks 136–145.
6. Keep test weeks out of statistical conclusions.
7. Label estimated revenue as revenue proxy, not profit.
8. Describe promotion and price findings as associations, not causes.
9. Save generated figures in `reports/figures/`.
10. Run focused tests and regenerate report outputs after pipeline changes.
