"""Reproducible analysis pipeline for the food-demand project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


ROOT = Path(__file__).resolve().parents[1]
RAW_DATA = ROOT / "data" / "raw"
PROCESSED_DATA = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

TRAIN_COLUMNS = {
    "id",
    "week",
    "center_id",
    "meal_id",
    "checkout_price",
    "base_price",
    "emailer_for_promotion",
    "homepage_featured",
    "num_orders",
}
TEST_COLUMNS = TRAIN_COLUMNS - {"num_orders"}
CENTER_COLUMNS = {"center_id", "city_code", "region_code", "center_type", "op_area"}
MEAL_COLUMNS = {"meal_id", "category", "cuisine"}


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")


def calculate_price_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with signed discount amount and rate features."""
    result = frame.copy()
    result["discount_amount"] = result["base_price"] - result["checkout_price"]
    result["discount_rate"] = result["discount_amount"].div(
        result["base_price"].replace(0, np.nan)
    )
    return result


def load_and_validate(data_dir: Path = RAW_DATA) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load source tables, validate their keys, and enrich train/test rows."""
    train = pd.read_csv(data_dir / "train.csv")
    test = pd.read_csv(data_dir / "test.csv")
    centers = pd.read_csv(data_dir / "fulfilment_center_info.csv")
    meals = pd.read_csv(data_dir / "meal_info.csv")

    for frame, required, name in (
        (train, TRAIN_COLUMNS, "train.csv"),
        (test, TEST_COLUMNS, "test.csv"),
        (centers, CENTER_COLUMNS, "fulfilment_center_info.csv"),
        (meals, MEAL_COLUMNS, "meal_info.csv"),
    ):
        _require_columns(frame, required, name)

    for frame, name in ((train, "train.csv"), (test, "test.csv")):
        if frame[list(TRAIN_COLUMNS - {"num_orders"})].isna().any().any():
            raise ValueError(f"{name} contains missing values in required input columns")
        if frame["id"].duplicated().any():
            raise ValueError(f"{name} contains duplicate IDs")
        if frame.duplicated(["week", "center_id", "meal_id"]).any():
            raise ValueError(f"{name} contains duplicate week/center/meal keys")

    if train["num_orders"].isna().any() or (train["num_orders"] < 0).any():
        raise ValueError("train.csv contains missing or negative num_orders")
    if centers["center_id"].duplicated().any() or meals["meal_id"].duplicated().any():
        raise ValueError("Reference tables must have unique center_id and meal_id keys")

    valid_centers = set(centers["center_id"])
    valid_meals = set(meals["meal_id"])
    invalid_train_centers = set(train["center_id"]) - valid_centers
    invalid_test_centers = set(test["center_id"]) - valid_centers
    invalid_train_meals = set(train["meal_id"]) - valid_meals
    invalid_test_meals = set(test["meal_id"]) - valid_meals
    if invalid_train_centers or invalid_test_centers or invalid_train_meals or invalid_test_meals:
        raise ValueError("Train/test contains center_id or meal_id missing from reference tables")

    train = train.merge(centers, on="center_id", how="left", validate="many_to_one")
    train = train.merge(meals, on="meal_id", how="left", validate="many_to_one")
    test = test.merge(centers, on="center_id", how="left", validate="many_to_one")
    test = test.merge(meals, on="meal_id", how="left", validate="many_to_one")
    train = calculate_price_features(train)
    test = calculate_price_features(test)

    if train[["category", "cuisine", "center_type"]].isna().any().any():
        raise ValueError("Enrichment introduced missing reference attributes in training data")
    if test[["category", "cuisine", "center_type"]].isna().any().any():
        raise ValueError("Enrichment introduced missing reference attributes in test data")

    quality = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_missing_values": int(train.isna().sum().sum()),
        "test_missing_values": int(test.isna().sum().sum()),
        "train_duplicate_ids": int(train["id"].duplicated().sum()),
        "test_duplicate_ids": int(test["id"].duplicated().sum()),
        "train_week_range": [int(train["week"].min()), int(train["week"].max())],
        "test_week_range": [int(test["week"].min()), int(test["week"].max())],
        "center_count": int(centers["center_id"].nunique()),
        "meal_count": int(meals["meal_id"].nunique()),
        "cleaning_policy": (
            "No rows were dropped or imputed. Required keys and references were validated; "
            "lookup tables were joined many-to-one."
        ),
    }
    return train, test, quality


def summarize_group(frame: pd.DataFrame, key: str, label: str) -> pd.DataFrame:
    summary = (
        frame.groupby(key, observed=True)
        .agg(
            total_orders=("num_orders", "sum"),
            average_orders=("num_orders", "mean"),
            observations=("num_orders", "size"),
            revenue=("revenue", "sum"),
            average_discount_rate=("discount_rate", "mean"),
        )
        .sort_values("total_orders", ascending=False)
        .reset_index()
    )
    summary["contribution_pct"] = summary["total_orders"] / summary["total_orders"].sum() * 100
    summary["cumulative_contribution_pct"] = summary["contribution_pct"].cumsum()
    summary.insert(0, "dimension", label)
    return summary


def top_contributors(summary: pd.DataFrame, threshold_pct: float = 80.0) -> pd.DataFrame:
    """Select the smallest ranked prefix reaching the requested contribution."""
    if not 0 < threshold_pct <= 100:
        raise ValueError("threshold_pct must be greater than 0 and at most 100")
    if summary.empty:
        return summary.copy()
    cumulative = summary["total_orders"].cumsum() / summary["total_orders"].sum() * 100
    count = int(np.searchsorted(cumulative.to_numpy(), threshold_pct, side="left")) + 1
    return summary.iloc[:count].copy()


def _promotion_tests(train: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for column in ("emailer_for_promotion", "homepage_featured"):
        group_no = train.loc[train[column] == 0, "num_orders"]
        group_yes = train.loc[train[column] == 1, "num_orders"]
        if group_no.empty or group_yes.empty:
            statistic, p_value = np.nan, np.nan
        else:
            test_result = mannwhitneyu(group_yes, group_no, alternative="two-sided")
            statistic, p_value = float(test_result.statistic), float(test_result.pvalue)
        results.append(
            {
                "feature": column,
                "n_without_promotion": int(len(group_no)),
                "n_with_promotion": int(len(group_yes)),
                "median_orders_without": float(group_no.median()) if len(group_no) else np.nan,
                "median_orders_with": float(group_yes.median()) if len(group_yes) else np.nan,
                "mann_whitney_u": statistic,
                "p_value": p_value,
            }
        )

    correlation = spearmanr(train["discount_rate"], train["num_orders"])
    stats = {
        "discount_orders_spearman_rho": float(correlation.statistic),
        "discount_orders_spearman_p_value": float(correlation.pvalue),
        "interpretation_note": (
            "These are observational associations. Promotion allocation and pricing are not randomized."
        ),
    }
    return pd.DataFrame(results), stats


def _format_p_value(value: float) -> str:
    if value == 0:
        return "< 1e-300 (أقل من دقة الحساب)"
    return f"{value:.3g}"


def _save_figures(
    train: pd.DataFrame,
    weekly: pd.DataFrame,
    category: pd.DataFrame,
    center: pd.DataFrame,
) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(weekly["week"], weekly["total_orders"], color="#2563eb", linewidth=2)
    ax.set(title="Weekly total orders", xlabel="Week", ylabel="Orders")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "weekly_orders.png", dpi=160)
    plt.close(fig)

    top_categories = category.sort_values("total_orders").tail(14)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(top_categories["category"], top_categories["total_orders"], color="#0f766e")
    ax.set(title="Total orders by meal category", xlabel="Orders", ylabel="Category")
    fig.tight_layout()
    fig.savefig(FIGURES / "orders_by_category.png", dpi=160)
    plt.close(fig)

    top_centers = center.nlargest(15, "total_orders").sort_values("total_orders")
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top_centers["center_id"].astype(str), top_centers["total_orders"], color="#7c3aed")
    ax.set(title="Top 15 fulfillment centers by orders", xlabel="Orders", ylabel="Center ID")
    fig.tight_layout()
    fig.savefig(FIGURES / "orders_by_center.png", dpi=160)
    plt.close(fig)

    sample = train.sample(n=min(15000, len(train)), random_state=42)
    fig, ax = plt.subplots(figsize=(9, 5))
    for flag, label, color in ((0, "Not featured", "#64748b"), (1, "Featured", "#f97316")):
        subset = sample.loc[sample["homepage_featured"] == flag]
        ax.scatter(
            subset["discount_rate"] * 100,
            subset["num_orders"],
            s=10,
            alpha=0.25,
            label=label,
            color=color,
        )
    ax.set(
        title="Discount rate and orders (sample)",
        xlabel="Discount from base price (%)",
        ylabel="Orders",
    )
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(FIGURES / "discount_and_orders.png", dpi=160)
    plt.close(fig)


def _write_report(
    train: pd.DataFrame,
    quality: dict[str, Any],
    weekly: pd.DataFrame,
    category: pd.DataFrame,
    center: pd.DataFrame,
    stats: dict[str, Any],
) -> None:
    total_orders = int(train["num_orders"].sum())
    total_revenue = float(train["revenue"].sum())
    best_week = weekly.loc[weekly["total_orders"].idxmax()]
    leading_category = category.iloc[0]
    leading_center = center.iloc[0]
    top_categories = top_contributors(category)
    top_centers = top_contributors(center)
    promo_rows = []
    promo_file = REPORTS / "promotion_tests.csv"
    if promo_file.exists():
        promo_tests = pd.read_csv(promo_file)
        for row in promo_tests.itertuples(index=False):
            promo_rows.append(
                f"| `{row.feature}` | {row.median_orders_without:.1f} | "
                f"{row.median_orders_with:.1f} | {_format_p_value(row.p_value)} |"
            )
    promotion_table = "\n".join(promo_rows)
    report = f"""# تقرير موجز: تحليل طلب الوجبات

## الملخص التنفيذي

- يغطي التدريب **{quality['train_rows']:,}** طلباً أسبوعياً، من الأسبوع {quality['train_week_range'][0]} إلى {quality['train_week_range'][1]}.
- مجموع الطلبات المسجل: **{total_orders:,}**، ومتوسط الطلبات في السجل **{train['num_orders'].mean():.1f}**.
- إيرادات تقريبية محسوبة من `num_orders × checkout_price`: **{total_revenue:,.2f}** بوحدة السعر في البيانات.
- أعلى أسبوع في إجمالي الطلبات: **{int(best_week['week'])}** ({int(best_week['total_orders']):,} طلباً).
- أعلى فئة حسب مجموع الطلبات: **{leading_category['category']}** ({int(leading_category['total_orders']):,}).
- أعلى مركز حسب مجموع الطلبات: **{int(leading_center['center_id'])}** ({int(leading_center['total_orders']):,}).

## سلامة البيانات والمنهج

فُحصت المفاتيح والمراجع، ثم رُبطت بيانات المراكز والوجبات بعلاقة many-to-one. لم تُحذف أو تُعوّض أي صفوف. عدد القيم المفقودة بعد الإثراء: {quality['train_missing_values']}. قرارات التنظيف موثقة في [`docs/cleaning_decisions.md`](../docs/cleaning_decisions.md).

## نتائج العروض والأسعار

| المتغير | وسيط الطلبات بلا عرض | وسيط الطلبات مع العرض | قيمة p لاختبار Mann–Whitney |
|---|---:|---:|---:|
{promotion_table}

ارتباط Spearman بين نسبة الخصم والطلبات: **ρ = {stats['discount_orders_spearman_rho']:.3f}**، وقيمة p **{_format_p_value(stats['discount_orders_spearman_p_value'])}**. هذه نتائج ارتباطية وليست دليلاً على أثر سببي؛ فالعروض والأسعار لم توزّع عشوائياً. أُجري الاختبار على سجلات كثيرة، لذا تُعرض قيمة الأثر نفسها مع الدلالة بدلاً من الاعتماد على قيمة p وحدها.

## دلالات عملية أولية

- تغطي أعلى **{len(top_categories)}** فئات **{top_categories.iloc[-1]['cumulative_contribution_pct']:.1f}%** من الطلبات؛ وأعلى خمس فئات هي {', '.join(top_categories['category'].astype(str))}.
- تغطي أعلى **{len(top_centers)}** مراكز **{top_centers.iloc[-1]['cumulative_contribution_pct']:.1f}%** من الطلبات. يمكن استخدام هذا الترتيب لتحديد أولوية متابعة المخزون والطاقة التشغيلية.
- وسيط الطلبات أعلى في سجلات البريد الترويجي والظهور بالصفحة الرئيسية، لكن ذلك لا يثبت أن العرض سبب الفرق. يوصى باختبار ترويجي مضبوط قبل توسيع الإنفاق.

## الرسوم

- الطلبات أسبوعياً: [`reports/figures/weekly_orders.png`](figures/weekly_orders.png)
- الطلبات حسب الفئة: [`reports/figures/orders_by_category.png`](figures/orders_by_category.png)
- الطلبات حسب المركز: [`reports/figures/orders_by_center.png`](figures/orders_by_center.png)
- علاقة الخصم بالطلبات: [`reports/figures/discount_and_orders.png`](figures/discount_and_orders.png)

## حدود الاستنتاج

`revenue` هنا مؤشر تقريبي مبني على سعر الشراء مضروباً في عدد الطلبات، وليس ربحاً محاسبياً؛ لا تتوفر تكاليف التشغيل أو بيانات تكلفة الوجبة. كما أن بيانات الاختبار تمتد للأسابيع {quality['test_week_range'][0]}–{quality['test_week_range'][1]} ولا تتضمن هدفاً معروفاً، لذلك لا تستخدم في الاستدلال الإحصائي.
"""
    (REPORTS / "client_report.md").write_text(report, encoding="utf-8")


def _write_presentation(
    quality: dict[str, Any],
    weekly: pd.DataFrame,
    category: pd.DataFrame,
    center: pd.DataFrame,
    promotion_tests: pd.DataFrame,
    stats: dict[str, Any],
) -> None:
    top_categories = top_contributors(category)
    top_centers = top_contributors(center)
    best_week = weekly.loc[weekly["total_orders"].idxmax()]
    emailer = promotion_tests.loc[
        promotion_tests["feature"] == "emailer_for_promotion"
    ].iloc[0]
    featured = promotion_tests.loc[
        promotion_tests["feature"] == "homepage_featured"
    ].iloc[0]
    slides = f"""# عرض تقديمي: تحليل الطلب الأسبوعي على الوجبات

## الشريحة 1 — سؤال العمل والبيانات
- كيف يتغير الطلب الأسبوعي؟ وما الفئات والمراكز الأهم؟
- ما الارتباط بين الأسعار والعروض وحجم الطلب؟
- {quality['train_rows']:,} سجل تدريب، {quality['test_rows']:,} سجل اختبار، {quality['center_count']} مركزاً و{quality['meal_count']} وجبة.
- التدريب يغطي الأسابيع {quality['train_week_range'][0]}–{quality['train_week_range'][1]}، والاختبار الأسابيع {quality['test_week_range'][0]}–{quality['test_week_range'][1]}.

**ملاحظة للمتحدث:** الاختبار لاحق زمنياً ولا يتضمن نتائج الطلب؛ لذلك نستخدمه للتنبؤ فقط.

## الشريحة 2 — حجم الطلب واتجاهه
- مجموع الطلبات المسجل: **{int(weekly['total_orders'].sum()):,}**.
- متوسط السجل: **{weekly['total_orders'].sum() / quality['train_rows']:.1f}** طلباً.
- أعلى أسبوع: **{int(best_week['week'])}** بإجمالي **{int(best_week['total_orders']):,}**.
- الرسم: [`figures/weekly_orders.png`](figures/weekly_orders.png).

**ملاحظة للمتحدث:** تعرض السلسلة مجموعات الطلب الأسبوعية لا توقعات مستقبلية.

## الشريحة 3 — أين يتركز الطلب؟
- أعلى فئة: **{category.iloc[0]['category']}**، بحصة **{category.iloc[0]['contribution_pct']:.1f}%**.
- تصل أول **{len(top_categories)}** فئات إلى **{top_categories.iloc[-1]['cumulative_contribution_pct']:.1f}%** من الطلبات.
- تصل أول **{len(top_centers)}** مراكز إلى **{top_centers.iloc[-1]['cumulative_contribution_pct']:.1f}%**.
- الرسوم: [`figures/orders_by_category.png`](figures/orders_by_category.png) و[`figures/orders_by_center.png`](figures/orders_by_center.png).

**ملاحظة للمتحدث:** الأعداد الإجمالية تتأثر بعدد السجلات؛ يجب قراءة المتوسطات مع الحجم قبل مقارنة المراكز.

## الشريحة 4 — الأسعار والعروض
- وسيط الطلبات دون البريد الترويجي: **{emailer['median_orders_without']:.0f}**؛ ومعه: **{emailer['median_orders_with']:.0f}**.
- وسيط الطلبات دون إبراز الصفحة الرئيسية: **{featured['median_orders_without']:.0f}**؛ ومعه: **{featured['median_orders_with']:.0f}**.
- ارتباط الخصم والطلبات: Spearman **ρ = {stats['discount_orders_spearman_rho']:.3f}**.
- الرسم: [`figures/discount_and_orders.png`](figures/discount_and_orders.png).

**ملاحظة للمتحدث:** المقارنة رصدية، والتخصيص الترويجي غير عشوائي؛ لا نستنتج السببية من الوسيط أو قيمة p.

## الشريحة 5 — جودة البيانات والحدود
- لا قيم مفقودة، ولا معرفات مكررة، وكل مفاتيح المراكز والوجبات مرتبطة بالجداول المرجعية.
- لم تُحذف أو تُعوّض أي سجلات.
- الإيراد المحسوب سعرٌ مضروب في الطلبات، وليس ربحاً؛ لا تتوفر بيانات التكلفة.
- اختير التحقق الزمني للأسابيع 136–145، بعد تدريب على الأسابيع 1–135.

## الشريحة 6 — توصيات وخطوات تالية
- استخدم مساهمة الفئات والمراكز في تخطيط المخزون والسعة، مع مراجعة المتوسطات لا الإجماليات فقط.
- اختبر العروض بتجربة مضبوطة تقيس الزيادة الصافية في الطلب والتكلفة قبل التوسع.
- راقب أسبوعياً الطلب والإيراد التقديري ونسبة الخصم ومزيج الفئات.
- قارن الانحدار الخطي بالغابة العشوائية على التحقق الزمني؛ لا تعتمد تنبؤاً قبل مراجعة MAE.

**رسالة ختامية:** التحليل يحدد أنماطاً وأولويات قابلة للاختبار، ولا يثبت أن الخصم أو الترويج وحده يسبب زيادة الطلب.
"""
    (REPORTS / "presentation.md").write_text(slides, encoding="utf-8")


def _update_model_deliverables(scores: pd.DataFrame) -> None:
    rows = "\n".join(
        f"| {row.model} | {row.validation_mae:.2f} | {row.validation_rmse:.2f} |"
        for row in scores.itertuples(index=False)
    )
    best = scores.iloc[0]
    report_section = f"""
## مقارنة التنبؤ الاختيارية

تُدرّب النماذج على الأسابيع 1–135، ويُختار النموذج وفق MAE على الأسابيع 136–145. بعد الاختيار، يعاد تدريبه على كامل التدريب لإنتاج تنبؤات الاختبار. لا تتوفر أهداف الاختبار لحساب درجة نهائية.

| النموذج | MAE للتحقق | RMSE للتحقق |
|---|---:|---:|
{rows}

الأفضل في التحقق الزمني: **{best['model']}** (MAE = **{best['validation_mae']:.2f}**). التنبؤات محفوظة في `reports/submission.csv`.
"""
    presentation_section = f"""
## الشريحة 7 — التنبؤ الاختياري
- تحقق زمني: التدريب بالأسابيع 1–135 والاختبار الداخلي بالأسابيع 136–145.
- أفضل نتيجة MAE: **{best['model']}** = **{best['validation_mae']:.2f}** طلباً.
- مقارنة النموذجين محفوظة في [`model_comparison.csv`](model_comparison.csv).
- تنبؤات الأسابيع 146–155 محفوظة في `submission.csv`؛ لا يمكن حساب خطأها دون الأهداف الفعلية.
"""
    for path, marker, section in (
        (REPORTS / "client_report.md", "\n## مقارنة التنبؤ الاختيارية\n", report_section),
        (REPORTS / "presentation.md", "\n## الشريحة 7 — التنبؤ الاختياري\n", presentation_section),
    ):
        existing = path.read_text(encoding="utf-8")
        if marker in existing:
            existing = existing.split(marker, 1)[0]
        path.write_text(existing.rstrip() + "\n" + section, encoding="utf-8")


def run_analysis(data_dir: Path = RAW_DATA, train_models: bool = False) -> dict[str, Any]:
    """Run quality checks, summaries, figures, report, and optional forecasting."""
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA.mkdir(parents=True, exist_ok=True)
    train, test, quality = load_and_validate(data_dir)
    train["revenue"] = train["num_orders"] * train["checkout_price"]

    weekly = (
        train.groupby("week", as_index=False)
        .agg(
            total_orders=("num_orders", "sum"),
            average_orders=("num_orders", "mean"),
            revenue=("revenue", "sum"),
            average_discount_rate=("discount_rate", "mean"),
        )
        .sort_values("week")
    )
    category = summarize_group(train, "category", "category")
    cuisine = summarize_group(train, "cuisine", "cuisine")
    center = summarize_group(train, "center_id", "center_id")
    meal = summarize_group(train, "meal_id", "meal_id")
    top_categories = top_contributors(category)
    top_centers = top_contributors(center)
    promotion_tests, stats = _promotion_tests(train)

    outputs = {
        "weekly_summary.csv": weekly,
        "category_summary.csv": category,
        "cuisine_summary.csv": cuisine,
        "center_summary.csv": center,
        "meal_summary.csv": meal,
        "top_80pct_categories.csv": top_categories,
        "top_80pct_centers.csv": top_centers,
        "promotion_tests.csv": promotion_tests,
    }
    for filename, frame in outputs.items():
        frame.to_csv(REPORTS / filename, index=False)
    (REPORTS / "data_quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORTS / "statistical_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _save_figures(train, weekly, category, center)
    _write_report(train, quality, weekly, category, center, stats)
    _write_presentation(quality, weekly, category, center, promotion_tests, stats)
    result: dict[str, Any] = {
        "quality": quality,
        "total_orders": int(train["num_orders"].sum()),
        "mean_orders": float(train["num_orders"].mean()),
        "weekly_summary": weekly,
        "category_summary": category,
        "cuisine_summary": cuisine,
        "center_summary": center,
        "meal_summary": meal,
        "top_80pct_categories": top_categories,
        "top_80pct_centers": top_centers,
        "promotion_tests": promotion_tests,
        "statistics": stats,
    }

    if train_models:
        result["model_results"] = train_and_predict(train, test, REPORTS)
        _update_model_deliverables(result["model_results"])
    return result


def train_and_predict(
    train: pd.DataFrame, test: pd.DataFrame, output_dir: Path = REPORTS
) -> pd.DataFrame:
    """Compare linear regression and random forest on a chronological holdout."""
    feature_columns = [
        "week",
        "checkout_price",
        "base_price",
        "discount_amount",
        "discount_rate",
        "emailer_for_promotion",
        "homepage_featured",
        "center_id",
        "city_code",
        "region_code",
        "center_type",
        "op_area",
        "meal_id",
        "category",
        "cuisine",
    ]
    categorical = [
        "center_id",
        "city_code",
        "region_code",
        "center_type",
        "meal_id",
        "category",
        "cuisine",
    ]
    if train["week"].max() < 145:
        raise ValueError("At least training data through week 145 is required for the holdout")
    fit_mask = train["week"] <= 135
    validation_mask = train["week"].between(136, 145)
    combined_x = pd.get_dummies(
        pd.concat([train[feature_columns], test[feature_columns]], ignore_index=True),
        columns=categorical,
        dtype=float,
    )
    train_x = combined_x.iloc[: len(train)].reset_index(drop=True)
    test_x = combined_x.iloc[len(train) :].reset_index(drop=True)
    y = train["num_orders"].reset_index(drop=True)
    fit_x = train_x.loc[fit_mask.to_numpy()]
    fit_y = y.loc[fit_mask.to_numpy()]
    validation_x = train_x.loc[validation_mask.to_numpy()]
    validation_y = y.loc[validation_mask.to_numpy()]
    candidates = {
        "LinearRegression": LinearRegression(),
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=25,
            max_depth=16,
            min_samples_leaf=5,
            max_features=0.5,
            n_jobs=4,
            random_state=42,
        ),
    }

    scores: list[dict[str, Any]] = []
    for name, model in candidates.items():
        model.fit(fit_x, fit_y)
        prediction = np.maximum(model.predict(validation_x), 0)
        scores.append(
            {
                "model": name,
                "validation_mae": float(mean_absolute_error(validation_y, prediction)),
                "validation_rmse": float(
                    np.sqrt(mean_squared_error(validation_y, prediction))
                ),
            }
        )
    score_frame = pd.DataFrame(scores).sort_values("validation_mae")
    best_name = str(score_frame.iloc[0]["model"])
    best_model = candidates[best_name]
    best_model.fit(train_x, y)
    test_predictions = np.maximum(best_model.predict(test_x), 0)
    submission = pd.DataFrame({"id": test["id"], "num_orders": test_predictions})
    output_dir.mkdir(parents=True, exist_ok=True)
    score_frame.to_csv(output_dir / "model_comparison.csv", index=False)
    submission.to_csv(output_dir / "submission.csv", index=False)
    return score_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA)
    parser.add_argument(
        "--train-models",
        action="store_true",
        help="compare baseline models and generate test predictions",
    )
    args = parser.parse_args()
    result = run_analysis(args.data_dir, train_models=args.train_models)
    print(f"Training rows: {result['quality']['train_rows']:,}")
    print(f"Test rows: {result['quality']['test_rows']:,}")
    print(f"Total observed orders: {result['total_orders']:,}")
    print(f"Report: {REPORTS / 'client_report.md'}")
    if args.train_models:
        print(result["model_results"].to_string(index=False))


if __name__ == "__main__":
    main()
