---
name: food-demand-analysis
description: Analyze and forecast weekly meal demand using the project's documented data-quality, statistical, and time-aware validation rules.
---

# Food demand analysis

- Preserve `data/raw/`; never modify the source CSV files.
- Use `src/food_demand_analysis.py` as the single source of truth for cleaning and reported metrics.
- Validate joins and unique keys before analyzing; do not silently drop or impute records.
- Describe price/promotion comparisons as associations, not causal effects.
- Keep the chronological holdout (weeks 136-145) separate from fitting (weeks 1-135).
- Regenerate the report and figures by running `python src\food_demand_analysis.py`.
- Regenerate the Arabic PowerPoint from verified report figures and model scores with `python src\create_presentation.py`.
- Regenerate optional predictions by adding `--train-models`.
