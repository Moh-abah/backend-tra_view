-- ============================================================================
-- heal-postgres.sql — إصلاح مستخدم/قاعدة/كلمة مرور Postgres بدون فقدان بيانات
-- ============================================================================
-- المشكلة: volume باسم postgres_data تمت تهيئته سابقاً بكلمة مرور مختلفة،
-- وPOSTGRES_PASSWORD لا يُطبَّق إلا عند أول تهيئة لـ volume فارغ، لذلك يفشل
-- الدخول برسالة: password authentication failed for user "trader".
--
-- هذا السكربت (يُنفَّذ عبر docker exec داخل حاوية Postgres — اتصال محلي موثوق):
--   1) يضمن وجود المستخدم trader (ينشئه إن كان مفقوداً)
--   2) يضبط كلمة مروره على trader_local_2024 (مطابقة لـ .env و docker-compose)
--   3) يضمن وجود قاعدة trading_db ويملكها trader
-- لا يمس أي بيانات موجودة — آمن للتكرار (idempotent).
-- ============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'trader') THEN
    CREATE ROLE trader LOGIN SUPERUSER PASSWORD 'trader_local_2024';
  ELSE
    ALTER USER trader WITH PASSWORD 'trader_local_2024';
  END IF;
END
$$;

SELECT 'CREATE DATABASE trading_db OWNER trader'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'trading_db')\gexec

GRANT ALL PRIVILEGES ON DATABASE trading_db TO trader;
