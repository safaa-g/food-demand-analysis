"""Build the Arabic PowerPoint deck from the verified project results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
OUTPUT = REPORTS / "presentation.pptx"

NAVY = RGBColor(16, 31, 55)
NAVY_LIGHT = RGBColor(27, 48, 78)
TEAL = RGBColor(20, 164, 150)
GOLD = RGBColor(240, 177, 77)
INK = RGBColor(35, 48, 67)
MUTED = RGBColor(105, 121, 141)
PAPER = RGBColor(247, 249, 252)
WHITE = RGBColor(255, 255, 255)
PALE_TEAL = RGBColor(229, 246, 243)
PALE_BLUE = RGBColor(233, 239, 249)
FONT = "Aptos"


def _rtl(paragraph) -> None:
    paragraph.alignment = PP_ALIGN.RIGHT
    paragraph._p.get_or_add_pPr().set("rtl", "1")


def _text(
    slide,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    size: float = 18,
    color: RGBColor = INK,
    bold: bool = False,
    align=PP_ALIGN.RIGHT,
    rtl: bool = True,
    font: str = FONT,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.04)
    frame.margin_right = Inches(0.04)
    frame.margin_top = Inches(0.015)
    frame.margin_bottom = Inches(0.015)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    if rtl:
        _rtl(paragraph)
    run = paragraph.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run._r.get_or_add_rPr().set("lang", "ar-SA" if rtl else "en-US")
    return box


def _set_background(slide, color: RGBColor = PAPER) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _rounded_card(slide, x, y, width, height, fill=WHITE, radius=MSO_SHAPE.ROUNDED_RECTANGLE):
    shape = slide.shapes.add_shape(
        radius, Inches(x), Inches(y), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    return shape


def _base_slide(prs: Presentation, title: str, number: int, eyebrow: str = "النتائج والتحليل"):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background(slide)
    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(12.96), Inches(0), Inches(0.37), Inches(7.5)
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = NAVY
    accent.line.fill.background()
    _text(slide, eyebrow, 0.66, 0.32, 2.6, 0.28, size=10, color=TEAL, bold=True)
    _text(slide, title, 0.66, 0.69, 11.9, 0.61, size=25, color=NAVY, bold=True)
    divider = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.7), Inches(1.4), Inches(0.8), Inches(0.045)
    )
    divider.fill.solid()
    divider.fill.fore_color.rgb = TEAL
    divider.line.fill.background()
    _text(slide, "تحليل الطلب الأسبوعي على الوجبات", 0.66, 7.11, 5.0, 0.2, size=9, color=MUTED)
    _text(slide, f"{number:02d}", 12.0, 7.08, 0.55, 0.25, size=9, color=MUTED, rtl=False, align=PP_ALIGN.CENTER)
    return slide


def _bullet_list(slide, items: list[str], x=7.16, y=1.84, width=5.05, line_height=0.91, size=17):
    for index, item in enumerate(items):
        top = y + index * line_height
        _rounded_card(slide, x, top, width, line_height - 0.12)
        dot = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(x + width - 0.44),
            Inches(top + 0.28),
            Inches(0.13),
            Inches(0.13),
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = TEAL if index % 2 == 0 else GOLD
        dot.line.fill.background()
        _text(
            slide,
            item,
            x + 0.19,
            top + 0.1,
            width - 0.72,
            line_height - 0.29,
            size=size,
            color=INK,
        )


def _add_picture(slide, filename: str, x=0.67, y=1.85, width=6.12, height=4.48):
    path = FIGURES / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required presentation chart was not found: {path}")
    _rounded_card(slide, x - 0.08, y - 0.08, width + 0.16, height + 0.16)
    slide.shapes.add_picture(
        str(path), Inches(x), Inches(y), width=Inches(width), height=Inches(height)
    )


def _stat_card(slide, x, y, width, label, value, detail, color=TEAL):
    _rounded_card(slide, x, y, width, 1.31)
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(x + width - 0.09),
        Inches(y + 0.12),
        Inches(0.045),
        Inches(1.06),
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = color
    bar.line.fill.background()
    _text(slide, label, x + 0.13, y + 0.12, width - 0.37, 0.28, size=11, color=MUTED)
    _text(slide, value, x + 0.13, y + 0.4, width - 0.37, 0.48, size=24, color=NAVY, bold=True)
    _text(slide, detail, x + 0.13, y + 0.91, width - 0.37, 0.22, size=9, color=MUTED)


def _read_model_scores() -> list[dict[str, str]]:
    path = REPORTS / "model_comparison.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def build_presentation(output_path: Path = OUTPUT) -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "تحليل الطلب الأسبوعي على الوجبات"
    prs.core_properties.subject = "تحليل البيانات، العروض، التنبؤ والتوصيات"
    prs.core_properties.author = "مشروع تحليل بيانات الطلب"
    prs.core_properties.keywords = "تحليل بيانات، طلب الوجبات، توقع الطلب"

    scores = _read_model_scores()
    slide_count = 7 if scores else 6

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_background(slide, NAVY)
    slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(9.72), Inches(0.24), Inches(3.25), Inches(3.25)
    ).fill.solid()
    slide.shapes[-1].fill.fore_color.rgb = NAVY_LIGHT
    slide.shapes[-1].line.fill.background()
    slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(0.18), Inches(5.3), Inches(1.65), Inches(1.65)
    ).fill.solid()
    slide.shapes[-1].fill.fore_color.rgb = NAVY_LIGHT
    slide.shapes[-1].line.fill.background()
    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(12.96), Inches(0), Inches(0.37), Inches(7.5)
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = TEAL
    accent.line.fill.background()
    _text(slide, "تحليل البيانات • تقرير تنفيذي", 0.85, 1.14, 5.8, 0.42, size=15, color=GOLD, bold=True)
    _text(
        slide,
        "تحليل الطلب\nالأسبوعي على الوجبات",
        0.82,
        1.85,
        8.45,
        1.75,
        size=34,
        color=WHITE,
        bold=True,
    )
    _text(
        slide,
        "رؤى تشغيلية عن الطلب والفئات والعروض، مع مقارنة زمنية لنماذج التنبؤ.",
        0.88,
        3.92,
        7.9,
        0.65,
        size=17,
        color=RGBColor(216, 227, 240),
    )
    _stat_card(slide, 0.88, 5.14, 2.3, "سجلات التدريب", "456,548", "145 أسبوعاً تاريخياً", TEAL)
    _stat_card(slide, 3.36, 5.14, 2.3, "سجلات الاختبار", "32,573", "10 أسابيع لاحقة", GOLD)
    _stat_card(slide, 5.84, 5.14, 2.3, "نقاط الخدمة", "77 مركزاً", "51 وجبة", TEAL)
    _text(slide, f"عرض تنفيذي  |  {slide_count} شرائح", 0.9, 6.91, 4.2, 0.22, size=10, color=RGBColor(183, 199, 220))

    slide = _base_slide(prs, "الطلب عبر الزمن: صورة واضحة للموسمية", 2)
    _add_picture(slide, "weekly_orders.png")
    _bullet_list(
        slide,
        [
            "إجمالي الطلبات المسجلة 119,557,485 طلباً.",
            "متوسط الطلب في السجل 261.9 طلباً.",
            "بلغ الإجمالي ذروته في الأسبوع 48: 1,303,457 طلباً.",
            "الاختبار يغطي الأسابيع 146–155، بعد فترة التدريب.",
        ],
        size=16,
    )
    _text(slide, "تنبيه: الرسم يصف الطلب التاريخي، ولا يمثل توقعاً للمستقبل.", 7.28, 5.79, 4.72, 0.46, size=11, color=MUTED)

    slide = _base_slide(prs, "تركيز الطلب حسب الفئة ومركز التوصيل", 3)
    _add_picture(slide, "orders_by_category.png", x=0.67, y=1.82, width=5.95, height=3.75)
    _add_picture(slide, "orders_by_center.png", x=6.84, y=1.82, width=5.62, height=3.75)
    _stat_card(slide, 0.82, 5.76, 3.77, "الفئة الأولى", "Beverages", "33.9% من الطلبات", TEAL)
    _stat_card(slide, 4.77, 5.76, 3.77, "تركيز الفئات", "81.4%", "تجمعها أعلى خمس فئات", GOLD)
    _stat_card(slide, 8.72, 5.76, 3.77, "تركيز المراكز", "80.6%", "عبر 51 مركزاً من 77", TEAL)

    slide = _base_slide(prs, "الأسعار والعروض: ارتباط لا يثبت السببية", 4)
    _add_picture(slide, "discount_and_orders.png", x=0.67, y=1.85, width=6.02, height=4.44)
    _bullet_list(
        slide,
        [
            "وسيط الطلب مع البريد الترويجي: 338؛ بدونه: 123.",
            "وسيط الطلب عند إبراز الوجبة: 350؛ بدونه: 123.",
            "ارتباط الخصم بالطلب ضعيف: Spearman ρ = 0.122.",
            "تخصيص العروض غير عشوائي؛ لا ننسب الفرق إلى العرض وحده.",
        ],
        size=15,
        line_height=0.97,
    )
    _rounded_card(slide, 7.15, 5.94, 5.0, 0.55, fill=PALE_TEAL)
    _text(slide, "التوصية: قياس أثر العروض بتجربة مضبوطة.", 7.34, 6.03, 4.62, 0.34, size=12, color=NAVY, bold=True)

    slide = _base_slide(prs, "جودة البيانات وحدود التفسير", 5)
    _stat_card(slide, 0.84, 1.83, 3.72, "اكتمال البيانات", "0 مفقود", "بعد ربط بيانات المراجع", TEAL)
    _stat_card(slide, 4.8, 1.83, 3.72, "سلامة المفاتيح", "0 تكرار", "معرّفات ومفاتيح تحليلية", GOLD)
    _stat_card(slide, 8.76, 1.83, 3.72, "قرارات التنظيف", "لا حذف", "ولا تعويض صامت للسجلات", TEAL)
    _bullet_list(
        slide,
        [
            "بيانات الاختبار بلا هدف معروف؛ لا يمكن قياس دقتها الفعلية.",
            "الإيراد التقديري يساوي السعر مضروباً في الطلبات؛ وليس ربحاً.",
            "النتائج رصدية؛ قد تؤثر خصائص الوجبة والمركز والتوقيت.",
        ],
        x=1.08,
        y=3.62,
        width=10.98,
        line_height=0.85,
        size=16,
    )

    slide = _base_slide(prs, "توصيات قابلة للتنفيذ", 6, eyebrow="من الرؤى إلى العمل")
    recommendations = [
        ("01", "تخطيط الإمداد", "استخدم حصص الفئات والمراكز لتوجيه المخزون والطاقة، مع متابعة المتوسط لكل سجل."),
        ("02", "اختبار العروض", "نفّذ تجربة مضبوطة تقيس الزيادة الصافية في الطلب والتكلفة قبل التوسع."),
        ("03", "مراقبة أسبوعية", "تابع الطلب ومزيج الفئات والخصومات لاكتشاف التغيرات مبكراً."),
        ("04", "حوكمة التنبؤ", "راقب MAE زمنياً وجدّد تقييم النموذج عند ورود أسابيع جديدة."),
    ]
    for i, (number, heading, body) in enumerate(recommendations):
        x = 0.86 + (i % 2) * 6.1
        y = 1.85 + (i // 2) * 2.08
        _rounded_card(slide, x, y, 5.7, 1.72)
        _text(slide, number, x + 4.88, y + 0.16, 0.56, 0.42, size=18, color=TEAL if i % 2 == 0 else GOLD, bold=True, rtl=False, align=PP_ALIGN.CENTER)
        _text(slide, heading, x + 0.24, y + 0.2, 4.45, 0.4, size=19, color=NAVY, bold=True)
        _text(slide, body, x + 0.24, y + 0.7, 5.05, 0.8, size=14, color=INK)
    _rounded_card(slide, 1.05, 6.26, 10.95, 0.54, fill=PALE_BLUE)
    _text(slide, "الخلاصة: الأنماط تحدد فرصاً واعدة للاختبار، لكنها لا تثبت وحدها أسباب زيادة الطلب.", 1.25, 6.34, 10.55, 0.34, size=13, color=NAVY, bold=True)

    if scores:
        slide = _base_slide(prs, "التنبؤ: مقارنة زمنية عادلة", 7, eyebrow="نتائج النموذج")
        scores.sort(key=lambda row: float(row["validation_mae"]))
        best = scores[0]
        _stat_card(slide, 0.84, 1.85, 3.72, "أفضل نموذج", "الغابة العشوائية", "اختير بناءً على MAE", TEAL)
        _stat_card(slide, 4.8, 1.85, 3.72, "MAE للتحقق", f"{float(best['validation_mae']):.2f}", "متوسط الخطأ المطلق بالطلبات", GOLD)
        _stat_card(slide, 8.76, 1.85, 3.72, "RMSE للتحقق", f"{float(best['validation_rmse']):.2f}", "جذر متوسط مربع الخطأ", TEAL)
        _text(slide, "تقسيم زمني يمنع تسرب المستقبل", 1.04, 3.64, 5.0, 0.42, size=19, color=NAVY, bold=True)
        _rounded_card(slide, 0.94, 4.18, 5.55, 1.5)
        _text(slide, "تدريب: الأسابيع 1–135", 1.18, 4.35, 4.95, 0.38, size=16, color=INK, bold=True)
        _text(slide, "تحقق: الأسابيع 136–145", 1.18, 4.88, 4.95, 0.38, size=16, color=INK, bold=True)
        _text(slide, "إعادة تدريب على كامل البيانات ثم توقع أسابيع الاختبار 146–155.", 6.88, 3.96, 5.16, 0.82, size=17, color=INK)
        _rounded_card(slide, 6.88, 5.02, 5.16, 0.82, fill=PALE_TEAL)
        _text(slide, "لا تتوفر أهداف الاختبار؛ لذلك لا توجد درجة أداء نهائية.", 7.1, 5.18, 4.74, 0.46, size=13, color=NAVY, bold=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build_presentation(args.output)
    check = Presentation(result)
    print(f"Created: {result}")
    print(f"Slides: {len(check.slides)}")
    print(f"Embedded charts: {sum(len(slide.shapes) for slide in check.slides if slide.shapes)} shapes")


if __name__ == "__main__":
    main()
