# تحليل الطلب الأسبوعي على الوجبات

مشروع تحليل بيانات الطلبات الأسبوعية لمراكز توصيل الوجبات. يختبر اتجاهات الطلب والفئات والمراكز والأسعار والعروض، ويوفر خياراً إضافياً لمقارنة نماذج التنبؤ.

## هيكل المشروع

- `data/raw/`: ملفات CSV الأصلية التي يستخدمها التحليل.
- `data/processed/`: مساحة للبيانات المجهزة.
- `src/food_demand_analysis.py`: خط التحليل والتحقق والتقارير.
- `notebooks/analysis.ipynb`: دفتر العمل التفاعلي.
- `reports/`: تقرير العميل والعرض بصيغة PowerPoint والجداول والرسوم ونتائج النماذج.
- `docs/cleaning_decisions.md`: قواعد التحقق والتجهيز.
- `.github/skills/food-demand-analysis/SKILL.md`: مهارة مخصصة لسياق المشروع.

## التشغيل

يتطلب Python 3.10 أو أحدث:

```powershell
python -m pip install -r requirements.txt
python src\food_demand_analysis.py
```

لإنشاء ملف العرض بصيغة PowerPoint بعد توليد الرسوم:

```powershell
python src\create_presentation.py
```

ينشئ الملف `reports/presentation.pptx` مع رسوم المشروع ونتائج التنبؤ إن كانت متاحة.

لتشغيل مقارنة الانحدار الخطي والغابة العشوائية وإنشاء ملف تنبؤات الاختبار:

```powershell
python src\food_demand_analysis.py --train-models
```

لتشغيل الاختبارات:

```powershell
python -m unittest discover -s tests -v
```

يُدرّب النموذجان على الأسابيع 1–135، ويُختار الأفضل وفق MAE على الأسابيع 136–145، ثم يعاد تدريبه على كامل التدريب قبل التنبؤ بأسابيع الاختبار 146–155. هذا فصل زمني يمنع استخدام المستقبل في التحقق.

## النتائج

بعد تشغيل المسار، راجع `reports/client_report.md`، ومخطط العرض `reports/presentation.md`، ورسوم `reports/figures/`، وملخصات CSV واختبارات الدلالة. ملف `reports/submission.csv` ينتج عند تشغيل خيار النماذج فقط.

## ملاحظات تفسيرية

إيرادات التقرير تقدير وصفي يساوي عدد الطلبات مضروباً بسعر الشراء، ولا يمثل هامش ربح. اختبارات Mann–Whitney وSpearman تصف ارتباطات في بيانات رصدية، ولا تثبت أن العرض أو الخصم تسبب في زيادة الطلب. لم تُحذف أو تُعوّض صفوف البيانات تلقائياً؛ تفاصيل القرارات في `docs/cleaning_decisions.md`.
