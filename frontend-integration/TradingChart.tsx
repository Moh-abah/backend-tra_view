/* ============================================================================
 * TradingChart.tsx — شارت احترافي بنمط TradingView مع تحميل لانهائي للشموع
 * ============================================================================
 * المزايا:
 *   • شموع حقيقية كاملة + فوليوم — ثيم داكن مطابق لـ TradingView
 *   • التمرير لليسار يجلب الشموع الأقدم تلقائيًا — بلا أي حد لعدد الشموع
 *     (عبر نقطة النهاية: /api/v1/market/candles/{market}/{symbol}?before=...)
 *   • بث حي عبر WS مع سقوط آمن إلى التحديث الدوري
 *   • تغيير الرمز/الفريم الزمني يعيد البناء من الصفر
 *
 * التثبيت في مشروع الفرونت:
 *   npm i lightweight-charts
 *
 * الاستخدام:
 *   <TradingChart apiBase="http://161.97.73.254:8000" symbol="BTCUSDT" market="crypto" timeframe="1h" />
 * ========================================================================== */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from "lightweight-charts";

/* ---------------------------- الإعدادات ---------------------------------- */
const PAGE_SIZE = 2000; // حجم الصفحة الواحدة — الإجمالي غير محدود
const TRIGGER_BARS = 80; // عدد الشموع المتبقية يسارًا قبل جلب الأقدم
const TF_MS: Record<string, number> = {
  "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
  "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
  "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000,
};
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

export const SUPPORTED_TFS = Object.keys(TF_MS);

/* ---------------------------- الأنواع ------------------------------------- */
interface Candle {
  time: number; // epoch SECONDS (lightweight-charts)
  open: number; high: number; low: number; close: number; volume: number;
}

interface CandlesPage {
  symbol: string; market: string; timeframe: string;
  candles: { time: number; open: number; high: number; low: number; close: number; volume: number }[];
  count: number; oldest_time: number | null; newest_time: number | null;
  has_more: boolean; next_before: number | null;
}

export interface TradingChartProps {
  apiBase?: string;            // مثل: http://localhost:8000
  symbol?: string;             // BTCUSDT
  market?: string;             // crypto | stocks
  timeframe?: string;          // 1h
  height?: number | string;
  onStatusChange?: (s: TradingChartStatus) => void;
}

export interface TradingChartStatus {
  loadedCandles: number;
  hasMore: boolean;
  live: boolean;
  state: string;
}

/* ========================================================================== */
export default function TradingChart({
  apiBase = "http://localhost:8000",
  symbol: initialSymbol = "BTCUSDT",
  market = "crypto",
  timeframe: initialTf = "1h",
  height = 520,
  onStatusChange,
}: TradingChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const dataRef = useRef<Candle[]>([]);
  const oldestMsRef = useRef<number | null>(null);
  const hasMoreRef = useRef(true);
  const loadingRef = useRef(false);
  const readyRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [symbol, setSymbol] = useState(initialSymbol.toUpperCase());
  const [tf, setTf] = useState(initialTf);
  const [symbolInput, setSymbolInput] = useState(initialSymbol.toUpperCase());
  const [live, setLive] = useState(false);
  const [stateTxt, setStateTxt] = useState("جاري التهيئة…");
  const [loaded, setLoaded] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [price, setPrice] = useState<number | null>(null);
  const [chg, setChg] = useState<{ d: number; p: number } | null>(null);

  const emit = useCallback((s: Partial<TradingChartStatus>) => {
    onStatusChange?.({
      loadedCandles: s.loadedCandles ?? dataRef.current.length,
      hasMore: s.hasMore ?? hasMoreRef.current,
      live: s.live ?? false,
      state: s.state ?? "",
    });
  }, [onStatusChange]);

  /* ---------------- تحويل شمعة الباك (ms) إلى شمعة الشارت (s) ------------- */
  const toBar = (c: { time: number; open: number; high: number; low: number; close: number; volume: number }): Candle => ({
    time: Math.floor(c.time / 1000) as UTCTimestamp,
    open: +c.open, high: +c.high, low: +c.low, close: +c.close, volume: +c.volume,
  });

  const volColor = (c: Candle) =>
    c.close >= c.open ? "rgba(38,166,154,.45)" : "rgba(239,83,80,.45)";

  const repaint = useCallback(() => {
    if (!candleRef.current || !volRef.current) return;
    candleRef.current.setData(dataRef.current as never);
    volRef.current.setData(dataRef.current.map(c => ({ time: c.time, value: c.volume, color: volColor(c) })) as never);
    setLoaded(dataRef.current.length);
    const n = dataRef.current.length;
    if (n >= 2) {
      const last = dataRef.current[n - 1], prev = dataRef.current[n - 2].close;
      setPrice(last.close);
      setChg({ d: last.close - prev, p: prev ? (last.close - prev) / prev * 100 : 0 });
    }
  }, []);

  /* ---------------- جلب صفحة شموع من الباك -------------------------------- */
  const fetchPage = useCallback(async (beforeMs: number | null): Promise<CandlesPage> => {
    const url =
      `${apiBase}/api/v1/market/candles/${market}/${symbol}?timeframe=${tf}&limit=${PAGE_SIZE}` +
      (beforeMs ? `&before=${beforeMs}` : "");
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }, [apiBase, market, symbol, tf]);

  /* ---------------- جلب الأقدم عند التمرير (بلا حد) ----------------------- */
  const loadOlder = useCallback(async (silent = false) => {
    if (loadingRef.current || !hasMoreRef.current || !readyRef.current || !chartRef.current) return;
    loadingRef.current = true;
    if (!silent) setStateTxt("جلب الشموع الأقدم…");
    try {
      const page = await fetchPage(oldestMsRef.current);
      const older = (page.candles || [])
        .map(toBar)
        .filter(c => !oldestMsRef.current || c.time * 1000 < oldestMsRef.current!);
      if (older.length) {
        const vr = chartRef.current!.timeScale().getVisibleLogicalRange();
        dataRef.current = older.concat(dataRef.current);
        repaint();
        if (vr) {
          chartRef.current!.timeScale().setVisibleLogicalRange({
            from: vr.from + older.length,
            to: vr.to + older.length,
          });
        }
        oldestMsRef.current = page.oldest_time ?? dataRef.current[0].time * 1000;
      }
      hasMoreRef.current = !!page.has_more;
      setHasMore(hasMoreRef.current);
      if (!hasMoreRef.current) setStateTxt("وصلت إلى بداية التاريخ المتاح");
      else if (!silent) setStateTxt("متصل");
    } catch (e) {
      if (!silent) setStateTxt(`تعذر جلب الأقدم: ${(e as Error).message}`);
    } finally {
      loadingRef.current = false;
      emit({ loadedCandles: dataRef.current.length, hasMore: hasMoreRef.current });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPage, repaint, emit]);

  /* ---------------- التحميل الأولي ---------------------------------------- */
  const initialLoad = useCallback(async () => {
    if (!chartRef.current) return;
    readyRef.current = false;
    hasMoreRef.current = true;
    loadingRef.current = false;
    dataRef.current = [];
    oldestMsRef.current = null;
    setStateTxt("جاري تحميل الشموع…");
    try {
      const page = await fetchPage(null);
      dataRef.current = (page.candles || []).map(toBar);
      oldestMsRef.current = page.oldest_time;
      hasMoreRef.current = !!page.has_more;
      repaint();
      chartRef.current.timeScale().scrollToRealTime();
      readyRef.current = true;
      setHasMore(hasMoreRef.current);
      setStateTxt("متصل");
      emit({ state: "متصل" });

      /* تعبئة مسبقة: صفحتان خلف الكادر حتى لا يظهر فراغ أبدًا */
      let prefetched = 0;
      while (hasMoreRef.current && prefetched < 2) {
        await loadOlder(true);
        prefetched++;
      }
    } catch (e) {
      setStateTxt(`فشل تحميل الشموع: ${(e as Error).message}`);
      emit({ state: "فشل" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPage, repaint, loadOlder, emit]);

  /* ---------------- البث الحي + الشبكة الأمان ------------------------------ */
  const applyLiveTick = useCallback((tick: { close: number; volume?: number; ts?: number }) => {
    const n = dataRef.current.length;
    if (!n || !candleRef.current || !volRef.current) return;
    const tfSec = Math.floor((TF_MS[tf] || 3_600_000) / 1000);
    const nowSec = tick.ts ? Math.floor(tick.ts / 1000) : Math.floor(Date.now() / 1000);
    const bucket = nowSec - (nowSec % tfSec);
    const last = { ...dataRef.current[n - 1] };
    let bar: Candle;
    if (bucket > last.time) {
      bar = { time: bucket as UTCTimestamp, open: tick.close, high: tick.close, low: tick.close, close: tick.close, volume: tick.volume || 0 };
      dataRef.current.push(bar);
    } else {
      bar = last;
      bar.close = tick.close;
      bar.high = Math.max(bar.high, tick.close);
      bar.low = Math.min(bar.low, tick.close);
      if (tick.volume) bar.volume = Math.max(bar.volume, tick.volume);
      dataRef.current[n - 1] = bar;
    }
    candleRef.current.update(bar as never);
    volRef.current.update({ time: bar.time, value: bar.volume, color: volColor(bar) } as never);
    setPrice(bar.close);
  }, [tf]);

  const connectWS = useCallback(() => {
    try {
      const wsProto = apiBase.startsWith("https") ? "wss" : "ws";
      // المسار الصحيح للبث اللحظي (يُركَّب تحت /api/v1/market في main.py)
      const ws = new WebSocket(`${wsProto}://${apiBase.replace(/^https?:\/\//, "")}/api/v1/market/ws/live/${market}/${symbol}?timeframe=${tf}`);
      wsRef.current = ws;
      ws.onopen = () => { setLive(true); setStateTxt("متصل — بث حي"); };
      ws.onmessage = (ev) => {
        try {
          const m = JSON.parse(ev.data);
          if (m.type === "price" && m.data?.close !== undefined) {
            applyLiveTick({
              close: +m.data.close,
              volume: +(m.data.volume || 0),
              ts: m.data.timestamp ? Date.parse(m.data.timestamp) : undefined,
            });
          }
        } catch { /* تجاهل الرسائل غير المفهومة */ }
      };
      ws.onclose = () => { setLive(false); setTimeout(connectWS, 8000); };
      ws.onerror = () => ws.close();
    } catch { setLive(false); }
  }, [apiBase, market, symbol, tf, applyLiveTick]);

  /* ---------------- دورة حياة الرسم --------------------------------------- */
  useEffect(() => {
    if (!wrapRef.current) return;
    const chart = createChart(wrapRef.current, {
      layout: { background: { type: ColorType.Solid, color: "#131722" }, textColor: "#d1d4dc", fontSize: 12 },
      grid: { vertLines: { color: "#1e222d" }, horzLines: { color: "#1e222d" } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#758696", width: 1, style: 3, labelBackgroundColor: "#363a45" },
        horzLine: { color: "#758696", width: 1, style: 3, labelBackgroundColor: "#363a45" },
      },
      rightPriceScale: { borderColor: "#2a2e39", scaleMargins: { top: 0.08, bottom: 0.25 } },
      timeScale: { borderColor: "#2a2e39", timeVisible: true, secondsVisible: false, rightOffset: 6, barSpacing: 8 },
      handleScroll: true, handleScale: true,
    });
    chartRef.current = chart;
    candleRef.current = chart.addCandlestickSeries({
      upColor: "#26a69a", downColor: "#ef5350",
      borderUpColor: "#26a69a", borderDownColor: "#ef5350",
      wickUpColor: "#26a69a", wickDownColor: "#ef5350",
    });
    volRef.current = chart.addHistogramSeries({
      priceScaleId: "", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false,
    });
    volRef.current.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    const ro = new ResizeObserver(entries => {
      const r = entries[0].contentRect;
      chart.applyOptions({ width: Math.floor(r.width), height: Math.floor(r.height) });
    });
    ro.observe(wrapRef.current);

    /* مُشغّل التمرير اللانهائي */
    const onRange = (range: { from: number; to: number } | null) => {
      if (!range || loadingRef.current || !hasMoreRef.current || !readyRef.current) return;
      if (range.from < TRIGGER_BARS) loadOlder(false);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);

    return () => {
      ro.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
      chart.remove();
      chartRef.current = null; candleRef.current = null; volRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadOlder]);

  /* تحميل البيانات عند تغيير الرمز/الفريم + تشغيل البث */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (wsRef.current) { try { wsRef.current.onclose = null; wsRef.current.close(); } catch { /* noop */ } wsRef.current = null; }
      setLive(false);
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      await initialLoad();
      if (cancelled) return;
      connectWS();
      pollRef.current = setInterval(async () => {
        if (!readyRef.current) return;
        try {
          const r = await fetch(`${apiBase}/api/v1/market/candles/${market}/${symbol}?timeframe=${tf}&limit=2`);
          if (!r.ok) return;
          const page: CandlesPage = await r.json();
          const newest = page.candles?.[page.candles.length - 1];
          if (newest) applyLiveTick({ close: +newest.close, volume: +newest.volume, ts: newest.time });
        } catch { /* الشبكة الأمان صامتة */ }
      }, 15_000);
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf, apiBase, market, initialLoad, connectWS, applyLiveTick]);

  /* ---------------- الواجهة ------------------------------------------------ */
  const up = chg ? chg.d >= 0 : true;
  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", background: "#131722", color: "#d1d4dc", borderRadius: 12, overflow: "hidden", border: "1px solid #2a2e39" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "8px 14px", background: "#1e222d", borderBottom: "1px solid #2a2e39" }}>
        <span style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>{symbol}</span>
        <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, background: live ? "rgba(38,166,154,.15)" : "rgba(120,123,134,.15)", color: live ? "#26a69a" : "#787b86" }}>
          {live ? "● مباشر" : "○ غير متصل"}
        </span>
        <span style={{ fontSize: 18, fontWeight: 700, fontVariantNumeric: "tabular-nums", color: up ? "#26a69a" : "#ef5350" }}>
          {price !== null ? price.toLocaleString("en-US", { maximumFractionDigits: 8 }) : "—"}
        </span>
        {chg && (
          <span style={{ fontSize: 12, fontWeight: 600, color: up ? "#26a69a" : "#ef5350" }}>
            {up ? "+" : ""}{chg.d.toFixed(2)} ({up ? "+" : ""}{chg.p.toFixed(2)}%)
          </span>
        )}
        <span style={{ flex: 1 }} />
        <input
          value={symbolInput}
          onChange={e => setSymbolInput(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === "Enter" && symbolInput.trim()) setSymbol(symbolInput.trim().toUpperCase()); }}
          placeholder="رمز… مثال: ETHUSDT"
          style={{ background: "#2a2e39", color: "#d1d4dc", border: "1px solid #363a45", borderRadius: 6, padding: "5px 10px", fontSize: 13, width: 140, outline: "none", direction: "ltr" }}
        />
      </div>

      {/* Timeframes */}
      <div style={{ display: "flex", gap: 2, padding: "6px 14px", background: "#1e222d", borderBottom: "1px solid #2a2e39" }}>
        {TIMEFRAMES.map(t => (
          <button
            key={t}
            onClick={() => setTf(t)}
            style={{
              padding: "5px 13px", fontSize: 12, fontWeight: 600, cursor: "pointer",
              color: t === tf ? "#fff" : "#787b86", background: t === tf ? "#2962ff" : "transparent",
              borderRadius: 5, border: "none",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div ref={wrapRef} style={{ position: "relative", width: "100%", height, minHeight: 320 }} />

      {/* Status */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", padding: "6px 14px", background: "#1e222d", borderTop: "1px solid #2a2e39", fontSize: 11.5, color: "#787b86" }}>
        <span>الشموع المحمّلة: <b style={{ color: "#d1d4dc" }}>{loaded.toLocaleString("en-US")}</b></span>
        <span>الفريم: <b style={{ color: "#d1d4dc" }}>{tf}</b></span>
        <span>الحالة: <b style={{ color: "#d1d4dc" }}>{stateTxt}</b></span>
        {!hasMore && <span style={{ color: "#787b86" }}>⏱ بداية التاريخ</span>}
        <span style={{ flex: 1 }} />
        <span style={{ opacity: 0.6 }}>التمرير لليسار يجلب الشموع الأقدم تلقائيًا — بلا حد</span>
      </div>
    </div>
  );
}
