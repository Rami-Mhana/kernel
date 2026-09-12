# Kernel — دحيح بيديا

Kernel is a lightweight YouTube-to-learning-library pipeline. It extracts channel
metadata, cleans and classifies episode topics, audits uncertain results, and builds
a searchable standalone HTML library with a local learner dashboard.

خط أنابيب يحوّل مكتبة فيديوهات YouTube إلى صفحة تعليمية واحدة قابلة للبحث والتصفح. المنتج مناسب لخدمة خمسات:

> أنظم مكتبة فيديوهات قناتك في مسار تعلمي واضح.

## التقنية

- Python و`yt-dlp` لجلب عناوين الفيديوهات والبيانات الوصفية.
- CSV اختياري كمرحلة وسيطة للمراجعة والتصنيف.
- HTML/CSS/JavaScript عادي في ملف واحد.
- لا توجد قاعدة بيانات أو خدمة Backend أو إطار واجهة.

The generated library is intentionally local-first: watch status, notes, profile name,
and theme are stored in browser `localStorage`. The local profile is a convenience
gate for separating one learner's state from the public library; it is not secure
authentication or cross-device synchronization.

## Kernel workflow

1. Fetch episode metadata from YouTube with `yt-dlp`.
2. Enrich descriptions while removing reference-heavy and promotional boilerplate.
3. Classify from the episode title first, then use description keywords as supporting
   evidence.
4. Audit low-confidence and conflicting records in CSV before publishing.
5. Build the standalone HTML library and test it in a browser.

The deterministic classifier is the source of truth for repeatable builds. An AI
provider can be added as a fallback for ambiguous records, but its suggestions must
remain auditable and must not replace the title-based rules silently.

### Reproducible audit workflow

The audit CSV is a review artifact, not an unchecked publication list:

```powershell
python scripts/classify_audit.py `
  --input data/episodes_dahih_with_desc.csv `
  --output data/episodes_classification_audit.csv `
  --raw-dir data/raw `
  --sample-size 100 `
  --seed 42
```

Audit generation uses `video_id` as the primary key, removes duplicate records, and
keeps the most complete duplicate. When the legacy enriched CSV does not contain
duration, thumbnail, or view-count fields, the generator hydrates them from the
local `data/raw/*.jsonl` cache. Existing manual decisions are matched by
`video_id` first and URL second.

Before building, review low-confidence, conflicting, uncategorized, and
missing-description records in the audit CSV. The script reports category coverage,
confidence distribution, missing metadata, and sample priority.

### Recommended rebuild sequence

```powershell
python scripts/fetch_episodes.py
python scripts/fetch_descriptions.py
python scripts/classify_audit.py
python scripts/build_demo.py
```

If metadata has already been fetched, skip the first command. If descriptions are
already cached, `fetch_descriptions.py` resumes instead of refetching completed rows.

## التشغيل على Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

يتطلب التشغيل وجود `yt-dlp` في البيئة. لإنشاء مكتبة من قناة أو قائمة تشغيل:

```powershell
python scripts/channel_to_webapp.py `
  "https://www.youtube.com/@CHANNEL/videos" `
  --name "اسم القناة" `
  --output "output/channel.html"
```

لتسريع التجربة دون جلب الأوصاف:

```powershell
python scripts/channel_to_webapp.py `
  "https://www.youtube.com/playlist?list=PLAYLIST_ID" `
  --name "اسم القائمة" `
  --skip-descriptions `
  --output "output/playlist.html"
```

ينتج الأمر ملف HTML مستقلًا يمكن فتحه محليًا أو نشره على Netlify أو GitHub Pages. يحتوي على البحث، التصنيف، الصور المصغرة، عدد الفيديوهات، وتجميع العناوين حسب المجال، وكل عنوان يفتح فيديو YouTube.

## مسار CSV الاختياري

لجلب البيانات فقط من رابط أو أكثر:

```powershell
python scripts/fetch_episodes.py `
  "https://www.youtube.com/@CHANNEL/videos" `
  --output "data/channel.csv"
```

يمكن إثراء CSV بالأوصاف عبر `scripts/fetch_descriptions.py`، ثم تشغيل `scripts/classify_audit.py` لإنشاء سجل تدقيق للعناصر منخفضة الثقة أو عينة ثابتة. التصنيف اقتراح عملي قابل للمراجعة وليس تصنيفًا أكاديميًا أو نشرًا آليًا.

## ديمو الدحيح

- القالب: [daheeh-demo.html](daheeh-demo.html)
- النسخة المبنية: [daheeh-demo-built.html](daheeh-demo-built.html)
- بيانات الأوصاف: [episodes_dahih_with_desc.csv](data/episodes_dahih_with_desc.csv)
- سجل تدقيق العينة: [episodes_classification_audit.csv](data/episodes_classification_audit.csv)
- اسم المنتج: **Kernel**

إعادة بناء الديمو:

```powershell
python scripts/build_demo.py
```

## عرض خدمة مقترح لخمسات

### العنوان

سأنظم مكتبة فيديوهات قناتك في صفحة تعليمية قابلة للبحث

### الوصف

لديك قناة مليئة بالمحتوى، لكن يصعب على المشاهد الوصول إلى الفيديو المناسب؟

سأحوّل روابط قناتك أو قوائم التشغيل إلى مكتبة HTML مرتبة وسهلة التصفح، مع تجميع الفيديوهات حسب الموضوع وإضافة البحث المباشر وروابط YouTube.

### ما ستحصل عليه

- صفحة HTML واحدة تعمل دون قاعدة بيانات أو Backend.
- جلب عناوين وروابط الفيديوهات من القناة أو قائمة التشغيل.
- تصنيف عملي قابل للتعديل حسب طبيعة المحتوى.
- بحث وتصفية وتجميع حسب التصنيف.
- ملف جاهز للنشر على Netlify أو GitHub Pages.

### المطلوب من العميل

رابط القناة أو قائمة التشغيل، واسم المكتبة، والتصنيفات الخاصة المطلوبة إن وجدت.

### ملاحظات مهمة

التصنيف آلي مبدئيًا ويحتاج مراجعة بشرية للعناصر منخفضة الثقة. تتضمن النسخة الحالية لوحة متابعة وملفًا شخصيًا محليًا وتصديرًا/استيرادًا للبيانات. لا تشمل الخدمة الحالية تسجيل دخول آمنًا أو قاعدة بيانات أو مزامنة بين الأجهزة.

### الديمو الحي

سيضاف رابط Netlify هنا بعد النشر: `رابط الديمو يُضاف بعد النشر`

## سير العمل الجديد

1. يجلب `yt-dlp` البيانات الخام، بما فيها `video_id` والصورة المصغرة والمدة ونوع المحتوى.
2. تُنظّف الأوصاف وتُزال النصوص الترويجية، ثم يُقترح التصنيف من قواعد محلية أو موفر AI اختياري.
3. تُراجع العناصر منخفضة الثقة والمتعارضة يدويًا في ملف التدقيق قبل بناء المكتبة.
4. يُبنى ملف HTML من القالب المشترك مع الاحتفاظ بالتعديلات اليدوية والصور المصغرة.
5. يمكن للمستخدم حفظ الفيديوهات، تحديد حالتها، وكتابة ملاحظات خاصة من لوحة المتابعة.

### لوحة المتابعة والملف المحلي

تدعم المكتبة وضعيات الحفظ، قيد المشاهدة، والمكتمل، بالإضافة إلى الملاحظات وحساب وقت المشاهدة. تُحفظ هذه البيانات في `localStorage` داخل المتصفح، ويمكن تصديرها إلى JSON واستيرادها لاحقًا. الملف الشخصي المحلي ليس تسجيل دخول آمنًا ولا يزامن البيانات بين الأجهزة.

يحتوي الاستيراد على تحقق من الإصدار وبنية بيانات الفيديو والحالة والملاحظات والمظهر.
يُطلب اسم ملف محلي قبل فتح لوحة المتابعة، مع بقاء البيانات داخل المتصفح فقط.

### المظهر والوصول

يوفر القالب أوضاع المظهر الفاتح والداكن ومظهر النظام، مع بحث وتصفية حسب التصنيف ونوع المحتوى وترتيب النتائج. يجب اختبار القالب على الهاتف وسطح المكتب مع اتجاه RTL، لوحة المفاتيح، الصور غير المتاحة، وتقليل الحركة.
