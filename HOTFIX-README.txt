═══════════════════════════════════════════════════════════════
 BACKEND v12.9 — HOTFIX (6 FILES) — التدقيق الشامل للنسخة المنشورة
═══════════════════════════════════════════════════════════════
النشر على الإنتاج:
  docker cp app/backtest/engine1.py      trading-backend:/app/app/backtest/engine1.py
  docker cp app/backtest/schemas.py      trading-backend:/app/app/backtest/schemas.py
  docker cp app/routers/backtest.py      trading-backend:/app/app/routers/backtest.py
  docker cp app/routers/backtest1.py     trading-backend:/app/app/routers/backtest1.py
  docker cp app/routers/strategies1.py   trading-backend:/app/app/routers/strategies1.py
  docker cp app/services/indicators/overlays.py trading-backend:/app/app/services/indicators/overlays.py
  docker restart trading-backend

الإصلاحات: A1 عمود العقد دائم (NaN→null) · A2 لا بادئة مزدوجة ×3 نقاط
A3 chart-data backtest1 (كان 404 دائماً) · A4 مرادف levels · A5 out_of_range
A6 strategies1/run نافذة كاملة · A7 فلترة الإشارات · A8 schema Optional

MD5 (يُطابق BACKEND_REPORT_ROUND12.1.md):
855e148c6f3f0a7b118cd4022ebceb38  app/backtest/engine1.py
0c127d29b5fd7bed0037c4f8d52608df  app/backtest/schemas.py
5e888e5182c40877ade0ca06a859d0fa  app/routers/backtest.py
4ef8fdde9af93f0de9edc3e1f54ddcc8  app/routers/backtest1.py
eb3d06742446986e539aed5d9264ecd9  app/routers/strategies1.py
c53be6cf92885c7f1ba42c3f26498e74  app/services/indicators/overlays.py
