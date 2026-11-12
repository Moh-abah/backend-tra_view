# عقد سيغما R45 — المصدر الحقيقي لكل حقول الفرونت-ند

> هذا المستند هو **مرجع وكيل الفرونت-ند الوحيد** لجولة 45: من أين تأتي
> كل قيمة، أي نقطة نهاية تخدمها، وماذا يتغير في السلوك. كل الأمثلة أدناه
> **ردود فعلية ملتقطة** من الإثبات الحي (34/34) فوق الراوترات الحقيقية.

## 1. القاعدة الذهبية الجديدة

| المفهوم | القيمة |
|---|---|
| معرّف العملية الظاهر للمستخدم | **رقم تسلسلي**: `10000001`, `10000002`, ... حتى `99999999` |
| مصدر الحالة والتقدم | **قاعدة البيانات** (جدول `backtest_tasks`) — لا الذاكرة |
| مصدر النتيجة الكاملة | جدول `backtest_runs` عبر `GET /backtest1/get/{backtest_id}` كما كان |
| المعرّفات السداسية القديمة | ما زالت تعمل في `/status` (توافق كامل) — لكن كل عملية **جديدة** رقمية |

**ما الذي يتغير في الواجهة الحالية؟ لا شيء إلزامي.** كل الحقول القديمة
(`task_id`, `state`, `message`, `backtest_id`, `result`, `error`) موجودة
بنفس أماكنها — الجديد كله **إضافي**. الترقيم يظهر تلقائياً لأن `task_id`
نفسه أصبح الرقم.

## 2. POST /api/v1/backtest1/run — بدء العملية

### الرد (وضع الموحد exit_strategy):
```json
{
  "success": true,
  "message": "Unified backtest (exit-strategy engine) started. Processing in background.",
  "task_id": "10000001",
  "task_number": 10000001,
  "status": "PROCESSING",
  "mode": "unified-exit",
  "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
  "poll": "/api/v1/backtest1/status/10000001"
}
```

### الجديد الذي يجب اعتماده:
- **`task_number`** (int): الرقم التسلسلي — اعرضه في شاشة Library مكان
  `f397b2fa` القديم (منسّق: `#10000001`).
- **`progress.percent/phase/message`**: الحالة الابتدائية للشريط.
- **`poll`**: مسار الاستطلاع الجاهز — استخدمه بدل بناء المسار يدوياً.

### وضع الانتظار `?wait=true`:
نفس عقد R44 السابق + الحقول الجديدة — يعيد `status: "COMPLETED"` مع
`summary` و`chart_data` كاملين في نفس الرد.

## 3. GET /api/v1/backtest1/status/{task_id} — الاستطلاع الحي

الرقمي (جديد) والسداسي (قديم) كلاهما يعمل. الرد الرقمي **الأغنى**:

### أثناء التشغيل (استطلاع كل 1-2 ثانية):
```json
{
  "task_id": "10000012",
  "task_number": 10000012,
  "state": "PROGRESS",
  "mode": "unified-exit",
  "name": "slow-progress-demo",
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "progress": {"percent": 25.0, "phase": "simulate", "message": "تنفيذ المحاكاة (استراتيجية zzfib) — جلب كامل: 240 شمعة"},
  "elapsed_seconds": 2.44,
  "eta_seconds": 7.3,
  "duration_ms": null,
  "stale_seconds": 0.1,
  "created_at": "2026-11-07T16:53:56.874851",
  "backtest_id": null,
  "message": "تنفيذ المحاكاة (استراتيجية zzfib) — جلب كامل: 240 شمعة"
}
```

| الحقل | المعنى للواجهة |
|---|---|
| `progress.percent` | شريط التقدم (0-100) |
| `progress.phase` | خطوات: `register` → `fetch` → `simulate` → `compute` → `save` → `done` |
| `progress.message` | نص عربي جاهز للعرض |
| `elapsed_seconds` | "كم مضى" — يتحدث حياً من القاعدة |
| `eta_seconds` | "كم بقي" — `null` إن لم يكن قابلاً للتقدير بعد (اعرض «جارٍ التقدير») |
| `stale_seconds` | نبض المهمة — إن تجاوز 300 ثانية والمهمة PROGRESS اعرض تحذيراً |

### بعد الاكتمال:
```json
{
  "state": "SUCCESS",
  "progress": {"percent": 100.0, "phase": "done", "message": "اكتملت العملية بنجاح وحُفظت النتيجة"},
  "duration_ms": 4036,
  "elapsed_seconds": 4.04,
  "backtest_id": "820bf8c700ec4169b7faa8de5a3d6761",
  "summary_stats": {"total_pnl_percent": 27.72, "win_rate": 56.52, "total_trades": 23},
  "meta": {"cache": {"hit": true, "cached": 240, "fetched_new": 0, "total": 240, "note": "full coverage from cache"}},
  "message": "Backtest completed successfully.",
  "result": {"status": "SUCCESS", "backtest_id": "820bf8c700ec4169b7faa8de5a3d6761"}
}
```

**بعد النجاح**: انتقل فوراً إلى `GET /backtest1/get/{backtest_id}` للوثيقة
الكاملة (نفس عقد R44: summary + chart_data + config + شموع بإثراءات
`ind_*` المسطّحة).

## 4. GET /api/v1/backtest1/tasks — **مصدر شاشة Library الجديد**

```
GET /tasks?limit=50&offset=0            ← الكل (الأحدث أولاً)
GET /tasks?state=PROGRESS               ← الجارية فقط
GET /tasks?state=SUCCESS                ← المنتهية فقط
```

```json
{
  "success": true,
  "count": 15,
  "stats": {"total": 15, "running": 1, "success": 14, "failure": 0},
  "data": [
    {
      "task_id": "10000016",
      "task_number": 10000016,
      "state": "SUCCESS",
      "mode": "unified-exit",
      "name": "سولانا ترند مع وقف خساره 20",
      "symbol": "BTCUSDT",
      "timeframe": "1h",
      "market": "crypto",
      "strategy": "zzfib",
      "days": 30,
      "progress": 100.0,
      "phase": "done",
      "backtest_id": "820bf8c700ec4169b7faa8de5a3d6761",
      "total_pnl_percent": 27.72,
      "win_rate": 56.52,
      "total_trades": 23,
      "duration_ms": 4036,
      "error": null,
      "meta": {"cache": {"hit": true, "fetched_new": 0}},
      "created_at": "2026-11-07T16:53:56.874851",
      "finished_at": "2026-11-07T16:54:00.906221",
      "elapsed_seconds": 4.04,
      "eta_seconds": null
    }
  ]
}
```

### خريطة شاشة Library الحالية ← الحقول الجديدة:

| ما يعرضه الشاشة اليوم | المصدر الجديد |
|---|---|
| `f397b2fa · — · — · 07/11/2026` | `task_number` منسّقاً `#10000001` + `created_at` |
| `WR —%` | `win_rate` (متوفر فور اكتمال العملية — لا حاجة لجلب الوثيقة الكاملة) |
| `— trades` | `total_trades` |
| (لا يوجد) | `state` + `progress` الحية للمهمة الجارية — **شريط تقدم داخل صف المكتبة** |
| (لا يوجد) | `duration_ms` → "استغرق 4.0 ث" |
| (لا يوجد) | `total_pnl_percent` |
| (لا يوجد) | `mode`: موحد/قياسي — وسم تشغيلي |

**سلوك التحميل من المكتبة**: عند اختيار عملية من القائمة خذ `backtest_id`
ثم `GET /backtest1/get/{backtest_id}` — يعيد بناء الإعدادات والنتائج
(`config` كامل في الوثيقة) بنفس آلية "حمّل باك تست سابق" الحالية.

## 5. GET /api/v1/backtest1/tasks/{task_id} — تفاصيل عملية واحدة

نفس عقد `/status` الرقمي تماماً (مصدر موحّد). للرقم غير الموجود: **404**
برسالة عربية صريحة. للمعرّف غير الرقمي: **422** يوجهك إلى `/status`.

## 6. GET /api/v1/backtest1/candle-cache — شفافية مصدر الشموع

```json
{
  "success": true,
  "count": 2,
  "data": [
    {
      "cache_key": "d:crypto:BTCUSDT:1h",
      "namespace": "d",
      "symbol": "BTCUSDT", "timeframe": "1h", "market": "crypto",
      "count": 240,
      "first_time_iso": "2026-10-23T18:00:00+00:00",
      "last_time_iso": "2026-11-02T17:00:00+00:00",
      "last_fetch_note": "full fetch (cold cache)",
      "updated_at": "2026-11-07T16:55:13.841563"
    }
  ]
}
```
`DELETE /backtest1/candle-cache/{cache_key}` يمسح مفتاحاً واحداً (يُعاد
جلبه كاملاً عند أول طلب تالٍ). مفيد لشاشة "إدارة البيانات".

## 7. سلوكيات يجب أن تعرفها الواجهة

1. **ETA قد تكون `null`** في أول ثانيتين (لا تاريخ ولا نسبة كافية بعد) —
   اعرض «جارٍ التقدير...» ولا تعتبرها خطأ.
2. **المهمة الجارية تُعرض في `/tasks` فوراً** (تظهر خلال أجزاء من الثانية
   من الضغط على زر التشغيل) — حدّث القائمة باستطلاع `/tasks` كل 2-3 ثوانٍ
   أو أعد الجلب عند اكتمال مهمة كنت تراقبها عبر `/status`.
3. **`stale_seconds`** إن تجاوزت 300 والمهمة PROGRESS — اعرض شارة تحذير
   («انقطع النبض»)؛ النظام سينظّفها تلقائياً بعد 30 دقيقة (reap) ويشفيعها
   إن اكتملت لاحقاً.
4. **أرقام العمليات لا تتكرر أبداً** — تصلح كمفتاح React ومسار مشاركة
   (`/library/10000001` مثلاً).
5. **كل التوقيتات UTC ISO** — حوّلها للعرض حسب المنطقة الزمنية للمستخدم.
6. **`meta.cache`** في `/status` و`/tasks` — معلومة شفافة عن مصدر الشموع
   (`hit/fetched_new/note`). اعرضها اختيارياً كوسم «من المخزون».

## 8. ما لم يتغير (لا تعيد بناءه)

- `GET /backtest1/get/{id}` — نفس عقد R44 كاملاً (شموع + ind_* مسطّحة).
- `GET /backtest1/{id}/chart-data` — نفسه.
- `GET /backtest1/list` — ما زال يعمل، لكن **`/tasks` هو الأفضل للمكتبة**
  (أسرع وأغنى ويشمل الجارية).
- `POST /backtest/run` (القياسي) — نفس الإضافات الجديدة مطبقة عليه
  (`task_number` + `/status` الرقمي عبر `backtest/status/{id}`).
- درع 422 لكتلة `exit_strategy` خارج المسار الموحد — حي كما هو (R43).
