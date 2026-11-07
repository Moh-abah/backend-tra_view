#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HOTFIX — إثبات إصلاح تعليق الباك-تست «معالجة» الأبدي (بلا قاعدة بيانات)
========================================================================
العطب الإنتاجي الموثق (سجل /app 2026-11-03 07:38):
    ImportError: cannot import name 'build_isolated_session_maker'
                 from 'app.database.session' (/app/app/database/session.py)
    → المهمة تبقى PROGRESS للأبد (سجلها المستخدم: «يضل في حاله معالجه»)

الجذبان:
  (1) نشر ناقص: حزمة ROUND19 شحنت app/routers/backtest.py دون
      app/database/session.py — الملف المستدعي وصل والملف المعرِّف قديم.
  (2) هشاشة بنيوية: الاستيرادات كانت خارج كتلة try في _run_backtest_inprocess
      — أي فشل استيراد يتحطم به بصمت قبل تسجيل FAILURE.

البراهين هنا (كلها ساكنة/محاكاة — لا DB ولا شبكة):
  [P1] اتساق الاستيراد الساكن: كل اسم مستورد من app.database.session / app.database
       في كامل app/ معرَّف فعلاً في الملفات المحلية (الصنف الذي فجّر الإنتاج).
  [P2] الحماية البنيوية: في _run_backtest_inprocess كل الاستيرادات داخل try،
       وكل مسارات الخروج (نجاح/مهلة/استثناء) تكتب حالة في _inprocess_tasks.
  [P3] سلسلة الاستدعاء: _execute_backtest يقبل session_maker، والدالة المعزولة
       تعيد (session_maker, engine).
  [P4] محاكاة العطب الإنتاجي حرفياً: وحدات مزيّفة بلا build_isolated_session_maker
       → النسخة الجديدة تسجّل FAILURE فوراً برسالة الاستيراد (بدل PROGRESS الأبدي).
  [P5] محاكاة مسار النجاح: وحدات مزيّفة كاملة → SUCCESS مع backtest_id.
  [P6] التوافق الخلفي: كل أسماء session.py الجيل السابق موجودة في الجديد
       (أي __init__.py قديم على أي حاوية سيستورد بلا كسر).
"""

import ast
import asyncio
import sys
import types
from pathlib import Path

PRO27 = Path("/home/z/my-project/backend-audit/pro27")
OLD27 = Path("/home/z/my-project/backend-audit/pro27_old")
sys.path.insert(0, str(PRO27))

FAILURES = []


def check(name, ok, detail=""):
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def defined_names(path: Path) -> set:
    tree = ast.parse(path.read_text())
    names = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.Assign):
            names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
    return names


# ============ [P1] اتساق الاستيراد الساكن ============
print("=" * 70)
print("[P1] اتساق الاستيراد الساكن — كامل app/")
session_names = defined_names(PRO27 / "app/database/session.py")
init_src = (PRO27 / "app/database/__init__.py").read_text()
init_tree = ast.parse(init_src)
init_exports = set()
for n in init_tree.body:
    if isinstance(n, ast.ImportFrom) and n.level >= 1 and n.module == "session":
        init_exports |= {a.name for a in n.names}
    elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        init_exports.add(n.name)
    elif isinstance(n, ast.Assign):
        init_exports |= {t.id for t in n.targets if isinstance(t, ast.Name)}
# __init__ يعيد التصدير من .session — لا بأس بذلك
bad = []
for py in sorted(PRO27.glob("app/**/*.py")):
    try:
        tree = ast.parse(py.read_text())
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            targets, source = None, None
            if node.module == "app.database.session":
                targets, source = node.names, session_names
            elif node.module == "app.database":
                targets, source = node.names, (init_exports | session_names)
            if targets:
                for a in targets:
                    if a.name != "*" and a.name not in source:
                        bad.append(f"{py.relative_to(PRO27)}: {a.name}")
check("كل `from app.database(.session)? import X` محلول", not bad, ", ".join(bad) or f"session={len(session_names)} اسماً · init={len(init_exports)}")

# ============ [P2] الحماية البنيوية ============
print("=" * 70)
print("[P2] الحماية البنيوية لـ _run_backtest_inprocess")
bt_src = (PRO27 / "app/routers/backtest.py").read_text()
bt_tree = ast.parse(bt_src)
fn = next(n for n in ast.walk(bt_tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_backtest_inprocess")

imports_inside_try, imports_outside_try = 0, 0
for node in fn.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        imports_outside_try += 1
try_node = next((n for n in fn.body if isinstance(n, ast.Try)), None)
if try_node:
    for node in try_node.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports_inside_try += 1
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Import, ast.ImportFrom)) and sub not in try_node.body:
                pass  # استيرادات داخل دوال متداخلة — ضمن try
check("لا استيراد خارج try في جسم الدالة", imports_outside_try == 0,
      f"داخل try: {imports_inside_try}")
handler_names = {ast.unparse(h.type) for h in try_node.handlers if h.type}
check("معالجة المهلة والاستثناء العام", "asyncio.TimeoutError" in handler_names and "Exception" in handler_names, str(handler_names))
writes = 0
for h in try_node.handlers:
    for node in ast.walk(h):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Subscript) and getattr(t.value, "id", "") == "_inprocess_tasks":
                    writes += 1
check("كل معالج يكتب حالة المهمة (FAILURE مؤكد)", writes >= 2, f"كتابات داخل المعالجات: {writes}")

# ============ [P3] سلسلة الاستدعاء ============
print("=" * 70)
print("[P3] سلسلة الاستدعاء كاملة")
tasks_tree = ast.parse((PRO27 / "app/tasks/backtest_tasks.py").read_text())
exec_fn = next((n for n in tasks_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_execute_backtest"), None)
args = {a.arg for a in exec_fn.args.args} | {a.arg for a in exec_fn.args.kwonlyargs} if exec_fn else set()
check("_execute_backtest يقبل session_maker", exec_fn is not None and "session_maker" in args, str(sorted(args)))
bism = next((n for n in ast.parse((PRO27 / "app/database/session.py").read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name == "build_isolated_session_maker"), None)
ret_names = set()
if bism:
    for node in ast.walk(bism):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
            ret_names |= {getattr(e, "id", "?") for e in node.value.elts}
check("build_isolated_session_maker يعيد (session_maker, engine)", ret_names == {"iso_session_maker", "iso_engine"}, str(ret_names))

# ============ [P4]+[P5] محاكاة سلوكية للنسخة الجديدة ============
print("=" * 70)
print("[P4] محاكاة العطب الإنتاجي (استيراد ناقص) على النسخة الجديدة")
fn_src = ast.get_source_segment(bt_src, fn)

class _FakeLogger:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def exception(self, *a, **k): self.last = str(a)

def _make_ns():
    return {
        "asyncio": asyncio,
        "logger": _FakeLogger(),
        "_inprocess_tasks": {},
        "_INPROCESS_TIMEOUT_SECONDS": 30,
    }

# وحدات مزيّفة: session بلا الدالة (حرفياً عطب /app)
app_mod = types.ModuleType("app"); sys.modules["app"] = app_mod
db_pkg = types.ModuleType("app.database"); app_mod.database = db_pkg; sys.modules["app.database"] = db_pkg
sess_mod = types.ModuleType("app.database.session")  # ← بلا build_isolated_session_maker عمداً
db_pkg.session = sess_mod; sys.modules["app.database.session"] = sess_mod
tasks_pkg = types.ModuleType("app.tasks"); app_mod.tasks = tasks_pkg; sys.modules["app.tasks"] = tasks_pkg
bt_tasks = types.ModuleType("app.tasks.backtest_tasks")
async def _fake_exec(cfg, ref, session_maker=None): return "bt_fake"
bt_tasks._execute_backtest = _fake_exec
tasks_pkg.backtest_tasks = bt_tasks; sys.modules["app.tasks.backtest_tasks"] = bt_tasks

ns = _make_ns()
exec(compile(fn_src, "<new_fn>", "exec"), ns)
asyncio.run(ns["_run_backtest_inprocess"]("t_broken", {"name": "x"}))
st = ns["_inprocess_tasks"]["t_broken"]
check("عطب الاستيراد → FAILURE فوري (لا تعليق)", st.get("state") == "FAILURE", str(st)[:120])
check("رسالة العطب مفهومة في /status", "cannot import name" in st.get("error", ""), st.get("error", "")[:90])

print("=" * 70)
print("[P5] محاكاة مسار النجاح (وحدات مزيّفة كاملة)")
sess_mod.build_isolated_session_maker = lambda: ("maker_fake", types.SimpleNamespace(dispose=lambda: asyncio.sleep(0)))
ns2 = _make_ns()
exec(compile(fn_src, "<new_fn>", "exec"), ns2)
asyncio.run(ns2["_run_backtest_inprocess"]("t_ok", {"name": "y"}))
st2 = ns2["_inprocess_tasks"]["t_ok"]
check("النجاح → SUCCESS مع backtest_id", st2 == {"state": "SUCCESS", "backtest_id": "bt_fake"}, str(st2))

# ============ [P6] التوافق الخلفي ============
print("=" * 70)
print("[P6] التوافق الخلفي مع أي حاوية أقدم")
old_path = OLD27 / "app/database/session.py"
if old_path.exists():
    old_names = defined_names(old_path)
    gone = old_names - session_names
    check("كل أسماء الجيل السابق موجودة في الجديد (الجديد أُسوعة)", not gone, str(sorted(gone)) or f"{len(old_names)}→{len(session_names)}")
else:
    print("— pro27_old غير متاح — تخطٍّ")

print("=" * 70)
if FAILURES:
    print(f"❌ فشل {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("✅ كل البراهين ناجحة — الحزمة جاهزة للنشر")
