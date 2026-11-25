# تقرير التعديلات — Monitoring Bot
## Phase 1: Security, Telegram UX, Backend Reliability & CI

**المستودع:** `koomn1/monitoring-bot`  
**فرع العمل:** `codex/phase-1-security-hardening`  
**Pull Request:** [#1 — Phase 1: Harden webhook verification and admin confirmations](https://github.com/koomn1/monitoring-bot/pull/1)  
**الحالة:** التغييرات مرفوعة على فرع منفصل؛ لم يتم دمجها في `main` ولم يتم تنفيذ نشر إنتاجي.

---

## 1. الملخص التنفيذي

تركّز هذه المرحلة على تقوية مسارات التأكيد الإداري والـ webhooks، تحسين تشخيص إعدادات الخدمات من Telegram، وإضافة مسار CI آلي لتجميع الكود وتشغيل اختبارات الوحدة.

التغييرات الفعلية موزعة على أربع مناطق:

1. Telegram UX وسلامة تأكيد الأوامر الحساسة.
2. Backend webhook verification ومعالجة أحداث GitHub.
3. Configuration diagnostics والتوثيق.
4. Automated tests وGitHub Actions CI.

> ملاحظة مهمة: هذا التقرير يصف ما تغيّر فعليًا في هذا الـ PR فقط. لا يعني أن كل أجزاء النظام أُعيدت هيكلتها أو أن تحسينات الأداء الشاملة قد نُفذت.

---

## 2. Telegram UI / UX

### 2.1 تأكيد الأوامر الحساسة

تم تعديل آلية أزرار التأكيد في `bot/utils/keyboards.py`:

- إلغاء تضمين اسم الأمر والوسائط مباشرة داخل بيانات زر Telegram.
- إنشاء Confirmation Token عشوائي opaque باستخدام `secrets.token_urlsafe(18)`.
- ربط كل Token بمعرّف المستخدم الذي بدأ الأمر `user_id`.
- ربطه بالمحادثة التي بدأ منها الأمر `chat_id`.
- تحديد صلاحية التأكيد بخمس دقائق.
- جعل الرمز صالحًا لاستخدام واحد فقط؛ بعد التأكيد الصحيح يتم استهلاكه.
- الإبقاء على حد أقصى للرموز المعلقة داخل الذاكرة لمنع نموها بلا حدود.

### 2.2 التحقق عند الضغط على الزر

في `bot/main.py`:

- أصبح callback الخاص بالتأكيد يستدعي محلّل الرمز مع هوية صاحب الضغط والمحادثة الحالية.
- لا يُنفّذ التأكيد إذا ضغط مستخدم آخر على الزر.
- لا يُنفّذ التأكيد من محادثة مختلفة.
- الرمز المنتهي أو المستخدم سابقًا لا يعيد تنفيذ الأمر.
- أزيل مسار التأكيد القديم الذي كان يمرر اسم الأمر والوسائط مباشرة في callback data.

وفي `bot/core/router.py` أصبح تمرير هوية المستخدم والمحادثة إلى إنشاء أزرار التأكيد جزءًا من تدفق التوجيه.

### 2.3 تجربة المستخدم في /envcheck

تم توسيع تقرير `/envcheck` ليعرض:

- حالة متغيرات البيئة الأساسية والاختيارية.
- حالة مجموعات التكاملات ككل، لا مجرد وجود متغير منفرد.
- أسماء المتغيرات الناقصة لكل تكامل.
- عدم إظهار قيم المفاتيح أو الأسرار داخل Telegram.

أمثلة للمجموعات التي يتم فحصها: GitHub Actions، GitHub Webhook، Cloudflare، Sentry، Umami، Firebase، AI Assistant، Telegram وSupabase.

**حدود هذا الفحص:** هو فحص اكتمال إعدادات البيئة، وليس اختبار اتصال فعلي أو إثباتًا لصلاحية API token لدى مزود الخدمة.

---

## 3. Backend Security & Webhooks

### 3.1 GitHub HMAC signature

في `bot/api/server.py`:

- إضافة التحقق من ترويسة GitHub الرسمية `X-Hub-Signature-256`.
- حساب HMAC-SHA256 على الـ raw request body باستخدام `GITHUB_WEBHOOK_SECRET`.
- مقارنة التوقيع باستخدام `hmac.compare_digest` لتقليل مخاطر المقارنة غير الآمنة.
- رفض التوقيع المفقود أو غير الصحيح باستجابة HTTP 401.
- التحقق يتم على محتوى الطلب الخام نفسه، وليس على JSON بعد إعادة تحويله.

### 3.2 التوافق الخلفي

تم الإبقاء على ترويسة `X-Webhook-Secret` كمسار توافق للمرسلين الداخليين القدامى عندما لا تكون ترويسة GitHub الرسمية موجودة.

هذا التوافق مقصود لتقليل كسر التكاملات القديمة، لكنه يظل عقدًا أقدم وأقل ملاءمة من GitHub HMAC. يفضّل لاحقًا حصره في مسار داخلي واضح أو إزالته بعد التأكد من عدم اعتماد أي مرسل عليه.

### 3.3 أحداث GitHub

تمت إضافة معالجة للأحداث التالية:

- `ping`: إرجاع `pong` لتأكيد إعداد webhook.
- `workflow_run`: متابعة انتهاء Workflows وإرسال إشعار عند نجاح أو فشل Workflow اسمه يتضمن deploy.
- `deployment_status`: إرسال إشعار عند نجاح النشر أو فشله/حدوث خطأ.
- الاحتفاظ بمعالجة الحدث الداخلي القديم `deployment_success` للتوافق.

### 3.4 التنبيهات

تستخدم معالجة أحداث النشر خدمة الإشعارات الموجودة بالفعل لإبلاغ المسؤولين بنتيجة النشر بدل الاكتفاء باستقبال webhook بصمت.

---

## 4. Backend Refactoring & Architecture

التغييرات الهيكلية الفعلية في هذه المرحلة محدودة ومقصودة:

- نقل قرار صلاحية التأكيد إلى token resolver بدل الاعتماد على بيانات callback مكشوفة.
- جعل إنشاء التأكيد مسؤولية router مع تمرير سياق المستخدم والمحادثة.
- إبقاء منطق التحقق من GitHub signature ومعالجة الحدث في طبقة API.
- فصل فحص جاهزية التكاملات في helper قابل للاختبار `_integration_readiness`.
- عدم تغيير واجهات الخدمات الأساسية أو مخطط قاعدة البيانات في هذا التحديث.

**ما لم يحدث:** لم تتم إعادة كتابة بنية المشروع بالكامل، ولم يتم تغيير قاعدة البيانات أو إضافة migrations، ولم يتم استبدال نظام التخزين أو إطار Telegram.

---

## 5. Performance & Resource Considerations

لا يتضمن هذا الـ PR تحسين أداء شاملًا أو Benchmark يثبت انخفاض زمن الاستجابة أو استهلاك الذاكرة. لذلك لا ينبغي اعتباره Performance Refactor كاملًا.

التحسينات/الاعتبارات ذات الصلة التي نُفذت:

- استخدام HMAC على bytes الطلب مباشرة، دون الحاجة إلى إعادة تسلسل JSON للتحقق من التوقيع.
- حد أقصى قدره 200 Confirmation Token معلّق في الذاكرة.
- انتهاء صلاحية رموز التأكيد بعد 300 ثانية.
- إزالة بيانات الأمر والوسائط من callback data، والاكتفاء برمز قصير opaque.

### قيد تشغيلي يجب معرفته

تُخزّن رموز التأكيد حاليًا في ذاكرة العملية. وبالتالي:

- إعادة تشغيل البوت تُفقد الرموز المعلقة.
- تشغيل أكثر من worker/process قد يجعل الرمز الذي أنشأه worker غير معروف لدى worker آخر.
- هذا التصميم مناسب فقط مع افتراض تشغيل نسخة واحدة من العملية في الوقت الحالي.

إذا كان التشغيل متعدد النسخ أو مطلوبًا استمرار التأكيدات بعد restart، فالحل المستقبلي هو تخزين الرموز في Redis أو قاعدة بيانات مع TTL واستهلاك ذري single-use. لم تتم إضافة ذلك الآن لتجنب إدخال بنية تخزين جديدة دون مراجعة واعتماد.

---

## 6. Configuration & Documentation

تم تحديث `docs/04-environment-variables.md` ليتوافق مع حقول Sentry الموجودة في `bot/config.py`:

- توضيح أن `SENTRY_ORG_SLUG` و`SENTRY_PROJECT_SLUG` مطلوبان عند استخدام Sentry issue lookup.
- إضافة توثيق `SENTRY_WEBHOOK_SECRET` كسر مطلوب عند استقبال Sentry webhooks.

كما تم توسيع عرض `/envcheck` ليشمل متغيرات كانت غير ظاهرة في التقرير السابق، مثل:

- `TELEGRAM_ERROR_CHANNEL_ID`
- `CLOUDFLARE_PROJECT_NAME`
- `SENTRY_ORG_SLUG`
- `SENTRY_PROJECT_SLUG`
- `UMAMI_API_URL`
- `UMAMI_WEBSITE_ID`
- `FIREBASE_SERVICE_ACCOUNT_JSON`

---

## 7. Testing & Quality Gates

### اختبارات جديدة

#### `tests/unit/test_confirmation_security.py`
يتحقق من:

- رفض التأكيد من مستخدم مختلف.
- رفض التأكيد من محادثة مختلفة.
- قبول التأكيد من المستخدم والمحادثة الأصليين.
- عدم السماح باستخدام الرمز مرتين.
- انتهاء صلاحية الرمز بعد TTL.

#### `tests/unit/test_github_webhook.py`
يتحقق من:

- قبول GitHub HMAC صحيح.
- رفض التوقيع المفقود أو غير الصحيح.
- معالجة ping.
- إرسال تنبيه عند فشل Deploy Workflow.
- استمرار دعم الترويسة الداخلية القديمة.

#### `tests/unit/test_envcheck.py`
يتحقق من:

- عدم اعتبار التكامل جاهزًا عند نقص متغير واحد من مجموعته.
- عرض اسم المتغير الناقص.
- عدم تسريب قيم الأسرار في نتيجة الفحص.

### اختبارات تم تحديثها

- `tests/unit/test_admin_actions_and_errors.py`
- `tests/unit/test_router.py`

تم تحديثها لتتوافق مع واجهة إنشاء وحل Confirmation Tokens الجديدة.

### GitHub Actions CI

تمت إضافة `.github/workflows/python-ci.yml`، ويقوم بالآتي:

1. تشغيله على Pull Requests.
2. تشغيله عند Push إلى `main` وفروع `codex/**`.
3. إعداد Python 3.11.
4. تثبيت متطلبات `requirements-dev.txt`.
5. تنفيذ `compileall` على `bot` و`tests`.
6. تشغيل `pytest -q`.
7. استخدام صلاحية قراءة محتوى المستودع فقط في Workflow.

رابط متابعة التشغيل:  
[GitHub Actions](https://github.com/koomn1/monitoring-bot/actions)

**حالة الاختبارات:** يجب الرجوع إلى آخر تشغيل مرتبط بأحدث commit في PR؛ لا يُعتبر الاختبار ناجحًا إلا بعد انتهاء Job بحالة success.

---

## 8. الملفات التي تغيرت

| الملف | نوع التغيير |
|---|---|
| `.github/workflows/python-ci.yml` | إضافة CI workflow |
| `bot/api/server.py` | GitHub HMAC والتحقق ومعالجة الأحداث |
| `bot/core/router.py` | تمرير هوية المستخدم والمحادثة للتأكيد |
| `bot/main.py` | التحقق من Confirmation Token عند callback |
| `bot/modules/telegram_commands/handlers.py` | تطوير /envcheck |
| `bot/utils/keyboards.py` | رموز تأكيد آمنة ومؤقتة ومقيدة بالمالك |
| `docs/04-environment-variables.md` | تصحيح وتوسيع توثيق Sentry |
| `tests/unit/test_admin_actions_and_errors.py` | تحديث اختبارات التأكيد |
| `tests/unit/test_confirmation_security.py` | اختبارات أمان جديدة |
| `tests/unit/test_envcheck.py` | اختبارات تشخيص الإعدادات |
| `tests/unit/test_github_webhook.py` | اختبارات GitHub Webhook |
| `tests/unit/test_router.py` | تحديث اختبار تدفق التأكيد |

---

## 9. عناصر لم تُنفذ بعد / توصيات المرحلة التالية

هذه نقاط ظهرت أثناء مراجعة النطاق، لكنها ليست ضمن التعديلات المنفذة في هذا PR:

1. **Persistent confirmation storage:** نقل الرموز من الذاكرة إلى Redis/DB إذا كان التشغيل متعدد العمال أو مطلوبًا تحمل إعادة التشغيل.
2. **Webhook compatibility cleanup:** حصر أو إزالة `X-Webhook-Secret` القديم بعد مراجعة المرسلين الحاليين.
3. **Workflow implementation:** ملفات Deploy/Build/Rollback/Backup/Restore المشار إليها في الخدمات ليست ضمن ملفات Workflow الموجودة حاليًا في المستودع؛ يلزم تصميمها ومراجعة أسرارها وصلاحياتها قبل تفعيلها.
4. **Cancellation authorization:** مراجعة callback الإلغاء بصورة مستقلة؛ هذا التحديث شدّد مسار التأكيد، وليس كل أزرار callback في البوت.
5. **Performance baseline:** إضافة قياسات زمن الاستجابة واستهلاك الموارد قبل أي ادعاء بتحسن الأداء.
6. **Integration smoke tests:** اختبار الاتصال الفعلي بالخدمات باستخدام بيئة اختبار وأسرار مخصصة، بدل الاكتفاء بفحص وجود المتغيرات.
7. **Full UI review:** مراجعة بقية قوائم Telegram والرسائل والتنسيقات وتجربة الاستخدام لم تتم كإعادة تصميم شاملة في هذا PR.

---

## 10. حدود التنفيذ والسلامة

- التعديلات موجودة على فرع `codex/phase-1-security-hardening`.
- Pull Request #1 مفتوح للمراجعة.
- لم يتم الدمج في `main`.
- لم يتم النشر إلى الإنتاج.
- لم يتم تعديل بيانات الإنتاج.
- لم تتم إضافة migrations أو تعديل schema قاعدة البيانات.

## 11. الخلاصة

المرحلة الحالية تحسّن أمان تأكيد الأوامر الحساسة، توثيق GitHub webhooks، وضوح حالة إعداد التكاملات من Telegram، وتضيف أساسًا آليًا لتشغيل اختبارات Python على Pull Requests.

لكنها ليست إعادة هيكلة شاملة لكل Backend، ولا إعادة تصميم كاملة لواجهة Telegram، ولا تحسين أداء مثبتًا بالقياس. هذه نطاقات مستقلة تحتاج مراحل مراجعة وتنفيذ واختبار منفصلة.

**المرجع الأساسي للتغييرات:** [Pull Request #1](https://github.com/koomn1/monitoring-bot/pull/1)
