import { useMemo, useState } from "react";
import {
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fmtCm,
  fmtDateShort,
  fmtDateTime,
  fmtDay,
  fmtTime,
  fmtWeekday,
} from "./format";
import type { Colors } from "./theme";
import { useNarrow } from "./theme";
import type { Payload, Point, SeriesKey } from "./types";

export interface SeriesMeta {
  key: SeriesKey;
  label: string;
  color: (c: Colors) => string;
  width: number;
  dash?: string;
}

// Reihenfolge = Zeichenreihenfolge (Overwerder zuletzt = oben).
export const SERIES: SeriesMeta[] = [
  { key: "zollenspieker", label: "Zollenspieker (km 598,3)", color: (c) => c.gray, width: 1.4, dash: "6 4" },
  { key: "st_pauli", label: "St. Pauli (km 623,1)", color: (c) => c.gray, width: 1.4, dash: "1 5" },
  { key: "over", label: "Over – Messung (km 605,3)", color: (c) => c.over, width: 1.6 },
  { key: "overwerder", label: "Overwerder – Vorhersage", color: (c) => c.overwerder, width: 2.6 },
];

// Nur die mittleren Tide-Kennwerte als waagerechte Referenzlinien (schlank).
const REF_KEYS = ["MThw", "MTnw"];

type Row = { t: number } & Partial<Record<SeriesKey, number>>;

function toRows(series: Payload["series"]): Row[] {
  const map = new Map<number, Row>();
  for (const meta of SERIES) {
    const pts = series[meta.key];
    if (!pts) continue;
    for (const [iso, v] of pts) {
      const t = Date.parse(iso);
      let row = map.get(t);
      if (!row) {
        row = { t };
        map.set(t, row);
      }
      row[meta.key] = v;
    }
  }
  return [...map.values()].sort((a, b) => a.t - b.t);
}

export interface TideExtreme {
  t: number;
  v: number;
  high: boolean; // true = Flut (lokales Maximum), false = Ebbe (lokales Minimum)
}

// Naechste Tide-Scheitel der Overwerder-Vorhersage ab `now`: je bis zu zwei
// Flut- (lokales Maximum) und Ebbe-Scheitel (lokales Minimum), chronologisch.
function tideExtrema(pts: Point[] | undefined, now: number): TideExtreme[] {
  if (!pts || pts.length < 3) return [];
  const xs = pts.map(([iso, v]) => ({ t: Date.parse(iso), v }));
  const highs: TideExtreme[] = [];
  const lows: TideExtreme[] = [];
  for (let i = 1; i < xs.length - 1; i++) {
    if (xs[i].t < now) continue;
    const { t, v } = xs[i];
    if (v >= xs[i - 1].v && v > xs[i + 1].v) highs.push({ t, v, high: true });
    else if (v <= xs[i - 1].v && v < xs[i + 1].v) lows.push({ t, v, high: false });
  }
  return [...highs.slice(0, 2), ...lows.slice(0, 2)].sort((a, b) => a.t - b.t);
}

// Zeile am (oder naechsten) Zeitpunkt t – fuer die angeklickten Werte.
function nearestRow(rows: Row[], t: number): Row | undefined {
  let best: Row | undefined;
  let bestD = Infinity;
  for (const r of rows) {
    const d = Math.abs(r.t - t);
    if (d < bestD) {
      bestD = d;
      best = r;
    }
  }
  return best;
}

const HOUR = 3600 * 1000;

// Kleinere Ziehstrecke als das gilt als Tippen (Ablese-Linie), nicht als Zoom.
const MIN_ZOOM_SPAN = 30 * 60 * 1000;

// Standard-Zeitfenster wie BSH "nächste 2 Tage": etwas Vergangenheit plus der
// Vorhersageschwerpunkt nach vorne (12 h zurück, 36 h voraus).
const DEFAULT_BACK = 12 * HOUR;
const DEFAULT_FWD = 36 * HOUR;

// Kandidaten fuer Tick-Abstaende (h) – beim Reinzoomen werden feinere gewaehlt.
const TICK_STEPS = [1, 2, 3, 6, 12, 24, 48].map((h) => h * HOUR);

// Tick-Abstand so waehlen, dass ~7 (schmal) bzw. ~14 (breit) Ticks entstehen.
// Ohne Zoom faellt das auf die alten Defaults (DAY schmal, HALF_DAY breit).
function pickStep(span: number, narrow: boolean): number {
  const target = narrow ? 7 : 14;
  for (const s of TICK_STEPS) if (span / s <= target) return s;
  return TICK_STEPS[TICK_STEPS.length - 1];
}

const BERLIN_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: "Europe/Berlin",
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

// Offset (ms) der gesetzlichen Zeit (Europe/Berlin) gegenueber UTC zu `ms`.
// Ueber formatToParts (spec-sicher), nicht ueber String-Parsing von Date().
function berlinOffsetMs(ms: number): number {
  const p: Record<string, number> = {};
  for (const part of BERLIN_PARTS.formatToParts(ms))
    if (part.type !== "literal") p[part.type] = Number(part.value);
  const wall = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return wall - ms;
}

// Ticks an lokalen Mitternachts-/Mittagsgrenzen (Offset ueber Fenster ~konstant).
function makeTicks(min: number, max: number, step: number): number[] {
  const off = berlinOffsetMs(min);
  const start = Math.ceil((min + off) / step) * step;
  const out: number[] = [];
  for (let lt = start; lt - off <= max; lt += step) out.push(lt - off);
  return out;
}

export default function Chart({
  data,
  colors,
  hidden,
  showSurges = false,
}: {
  data: Payload;
  colors: Colors;
  hidden: Set<SeriesKey>;
  showSurges?: boolean;
}) {
  const narrow = useNarrow();

  // Zoom-Fenster (X-Bereich) und laufende Auswahl beim Ziehen.
  const [zoom, setZoom] = useState<[number, number] | null>(null);
  const [selLeft, setSelLeft] = useState<number | null>(null);
  const [selRight, setSelRight] = useState<number | null>(null);
  // Angeklickter Zeitpunkt: fixiert eine Ablese-Linie mit Werten je Serie.
  const [pinned, setPinned] = useState<number | null>(null);

  // Alles Abgeleitete in einem Memo, damit es nur bei data/narrow/hidden/zoom
  // neu rechnet (nicht bei jedem Render, z. B. Tooltip-Hover oder Drag).
  const {
    rows,
    visible,
    refLines,
    surgeLines,
    xDomain,
    yDomain,
    ticks,
    labelSet,
    dense,
    extrema,
    dayFirst,
    zoomed,
    xFull,
    brushStart,
    brushEnd,
    atFull,
  } = useMemo(() => {
      const rows = toRows(data.series);
      const present = SERIES.filter((m) => data.series[m.key]?.length);
      const visible = present.filter((m) => !hidden.has(m.key));
      const refLines = REF_KEYS.map((k) => ({ k, v: data.reference_lines[k] })).filter(
        (r) => typeof r.v === "number",
      );
      // Top-10-Sturmflut-Marken (nur wenn per Button eingeblendet).
      const surgeLines = showSurges ? (data.surge_lines ?? []) : [];
      const xs = rows.map((r) => r.t);
      const xMin = xs[0] ?? 0;
      const xMax = xs[xs.length - 1] ?? 0;
      // Standardausschnitt: 12 h zurück + 36 h voraus um "jetzt" (auf die
      // vorhandenen Daten begrenzt). Zoom übersteuert diesen Ausschnitt.
      const nowT = Date.parse(data.now);
      const dfltLo = Math.max(xMin, nowT - DEFAULT_BACK);
      const dfltHi = Math.min(xMax, nowT + DEFAULT_FWD);
      const zoomed = zoom !== null;
      const [x0, x1] = zoom ?? [dfltLo, dfltHi];

      // Y-Skala nur aus sichtbaren Serien im aktuellen X-Fenster ableiten,
      // damit Aus-/Einblenden und Zoom die Höhenachse mitziehen.
      let lo = Infinity;
      let hi = -Infinity;
      for (const r of rows) {
        if (r.t < x0 || r.t > x1) continue;
        for (const m of visible) {
          const v = r[m.key];
          if (typeof v === "number") {
            lo = Math.min(lo, v);
            hi = Math.max(hi, v);
          }
        }
      }
      // Referenzlinien (und eingeblendete Sturmflut-Marken) nur im Vollbild in
      // die Skala zwingen, damit die Achse sie umfasst.
      if (!zoomed) {
        for (const r of refLines) {
          lo = Math.min(lo, r.v as number);
          hi = Math.max(hi, r.v as number);
        }
        for (const s of surgeLines) {
          lo = Math.min(lo, s.cm);
          hi = Math.max(hi, s.cm);
        }
      }
      if (lo === Infinity) {
        lo = 0;
        hi = 100;
      }
      const pad = 20;
      const yLo = Math.floor((lo - pad) / 20) * 20;
      const yHi = Math.ceil((hi + pad) / 20) * 20;

      // Ticks alle 3 h, beschriftete Labels alle 6 h, solange das Fenster nicht
      // zu breit ist; bei weit herausgezoomten Fenstern adaptiv ausduennen.
      const span = x1 - x0;
      const dense = span <= 72 * HOUR;
      const tickStep = dense ? 3 * HOUR : pickStep(span, narrow);
      const labelStep = dense ? 6 * HOUR : tickStep;
      const tk = makeTicks(x0, x1, tickStep);
      // 6-h-Positionen sind eine Teilmenge der 3-h-Positionen (beide an lokalen
      // Grenzen ausgerichtet) -> markiert, welche Ticks eine Beschriftung tragen.
      const labelSet = new Set(makeTicks(x0, x1, labelStep));
      // Datumszeile nur beim ersten beschrifteten Tick eines Tages zeigen (wie BSH).
      const firsts = new Set<number>();
      let prevDay = "";
      for (const t of tk) {
        if (!labelSet.has(t)) continue;
        const d = fmtDay(t);
        if (d !== prevDay) {
          firsts.add(t);
          prevDay = d;
        }
      }
      // Naechste Tide-Scheitel (2x Flut / 2x Ebbe) fuer die Info-Box.
      const extrema = tideExtrema(data.series.overwerder, nowT);
      // Brush-Griffe auf die Datenzeilen abbilden, die das aktuelle X-Fenster
      // begrenzen. Die Übersichtsleiste zeigt den GESAMTEN Zeitraum; die Griffe
      // markieren darin den sichtbaren Ausschnitt (Standard oder Zoom).
      let bs = 0;
      let be = rows.length - 1;
      for (let i = 0; i < rows.length; i++)
        if (rows[i].t >= x0) {
          bs = i;
          break;
        }
      for (let i = rows.length - 1; i >= 0; i--)
        if (rows[i].t <= x1) {
          be = i;
          break;
        }
      if (be < bs) be = bs;
      // "Ganzer Zeitraum" ist erreicht, wenn das Fenster die Daten voll abdeckt.
      const atFull = x0 <= xMin + 1 && x1 >= xMax - 1;

      return {
        rows,
        visible,
        refLines,
        surgeLines,
        xDomain: [x0, x1] as [number, number],
        yDomain: [yLo, yHi] as [number, number],
        ticks: tk,
        labelSet,
        dense,
        extrema,
        dayFirst: firsts,
        zoomed,
        xFull: [xMin, xMax] as [number, number],
        brushStart: bs,
        brushEnd: be,
        atFull,
      };
    }, [data, narrow, hidden, zoom, showSurges]);

  const now = Date.parse(data.now);
  const fcStart = Date.parse(data.forecast_start);

  // Drag-to-Zoom: activeLabel ist der t-Wert (ms) am Cursor, am nächsten
  // Datenpunkt eingerastet (Recharts typisiert ihn als string -> Number()).
  const labelAt = (e: { activeLabel?: string | number } | null): number | null => {
    const v = e?.activeLabel;
    if (v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const onDown = (e: { activeLabel?: string | number } | null) => {
    const t = labelAt(e);
    if (t == null) return;
    setSelLeft(t);
    setSelRight(t);
  };
  const onMove = (e: { activeLabel?: string | number } | null) => {
    const t = labelAt(e);
    if (selLeft != null && t != null) setSelRight(t);
  };
  const onUp = () => {
    if (selLeft != null && selRight != null) {
      const a = Math.min(selLeft, selRight);
      const b = Math.max(selLeft, selRight);
      if (b - a >= MIN_ZOOM_SPAN) {
        // spuerbar gezogen -> zoomen
        setZoom([a, b]);
      } else {
        // getippt (oder minimal verrutscht) -> Ablese-Linie setzen/entfernen
        setPinned((prev) => (prev === a ? null : a));
      }
    }
    setSelLeft(null);
    setSelRight(null);
  };

  // Übersichtsleiste (Brush) verschieben/aufziehen: Griff-Indizes -> X-Fenster.
  // So lässt sich der sichtbare Ausschnitt über den ganzen Vorhersagezeitraum
  // schieben und beliebig verbreitern (nicht nur hineinzoomen).
  const onBrush = (r: { startIndex?: number; endIndex?: number }) => {
    if (r.startIndex == null || r.endIndex == null) return;
    const a = rows[r.startIndex]?.t;
    const b = rows[r.endIndex]?.t;
    if (a == null || b == null || b <= a) return;
    setZoom([a, b]);
  };

  // Werte je sichtbarer Serie am angeklickten Zeitpunkt (fuer die Ablese-Linie).
  const pinRow = pinned == null ? undefined : nearestRow(rows, pinned);
  const pinVals =
    pinRow == null
      ? []
      : visible
          .map((m) => ({ m, v: pinRow[m.key] }))
          .filter((e): e is { m: SeriesMeta; v: number } => typeof e.v === "number");

  return (
    <div className="chart-wrap">
      <div className="chart-controls">
        {!atFull && (
          <button
            type="button"
            className="chart-btn"
            onClick={() => setZoom(xFull)}
            title="Gesamten verfügbaren Vorhersagezeitraum anzeigen"
          >
            Ganzer Zeitraum
          </button>
        )}
        {zoomed && (
          <button
            type="button"
            className="chart-btn"
            onClick={() => {
              setZoom(null);
              setPinned(null);
            }}
          >
            Zoom zurücksetzen
          </button>
        )}
      </div>
      {extrema.length > 0 && (
        <div
          className="tide-info"
          style={{ borderColor: colors.overwerder, color: colors.overwerder }}
        >
          <div className="tide-info-title">Nächste Scheitel Over</div>
          {extrema.map((e) => (
            <div key={e.t} className="tide-info-row">
              <span className="tide-info-kind">{e.high ? "Flut" : "Ebbe"}</span>
              <span className="tide-info-time">
                {fmtDateShort(e.t)} {fmtTime(e.t)}
              </span>
              <span className="tide-info-val">{fmtCm(e.v)}</span>
            </div>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={rows}
          margin={{ top: 16, right: 16, bottom: 8, left: 4 }}
          onMouseDown={onDown}
          onMouseMove={onMove}
          onMouseUp={onUp}
          onMouseLeave={onUp}
          onDoubleClick={() => {
            setZoom(null);
            setPinned(null);
          }}
        >
          <CartesianGrid stroke={colors.grid} vertical={false} />
        <XAxis
          type="number"
          dataKey="t"
          scale="time"
          domain={xDomain}
          allowDataOverflow
          ticks={ticks}
          tickLine={false}
          axisLine={{ stroke: colors.axis }}
          tick={(props) => (
            <TimeTick
              {...props}
              colors={colors}
              dayFirst={dayFirst}
              labelSet={labelSet}
              dense={dense}
              narrow={narrow}
            />
          )}
          height={40}
          interval={0}
        />
        <YAxis
          type="number"
          domain={yDomain}
          allowDataOverflow
          width={54}
          tickLine={false}
          axisLine={false}
          tick={{ fill: colors.muted, fontSize: 11 }}
          label={{
            value: "cm über PNP",
            angle: -90,
            position: "insideLeft",
            style: { fill: colors.secondary, fontSize: 11, textAnchor: "middle" },
          }}
        />

        {refLines.map((r) => (
          <ReferenceLine
            key={r.k}
            y={r.v as number}
            stroke={colors.ref}
            strokeDasharray="2 4"
            ifOverflow={zoomed ? "hidden" : "extendDomain"}
            label={{
              value: `${r.k} ${Math.round(r.v as number)}`,
              position: "insideTopLeft",
              fill: colors.muted,
              fontSize: 10,
            }}
          />
        ))}

        {surgeLines.map((s, i) => (
          <ReferenceLine
            key={`surge-${s.rank}`}
            y={s.cm}
            stroke={colors.surge}
            strokeWidth={1}
            ifOverflow={zoomed ? "hidden" : "extendDomain"}
            label={{
              value: `#${s.rank} ${s.label} ${Math.round(s.cm)}`,
              // dicht beieinanderliegende Marken abwechselnd links/rechts, damit
              // sich die Beschriftungen nicht ueberlagern.
              position: i % 2 === 0 ? "insideBottomRight" : "insideBottomLeft",
              fill: colors.surge,
              fontSize: 10,
            }}
          />
        ))}

        <ReferenceLine
          x={fcStart}
          stroke={colors.forecast}
          strokeDasharray="4 4"
          label={{
            value: "Vorhersagebeginn",
            position: "insideBottomLeft",
            fill: colors.forecast,
            fontSize: 10,
          }}
        />
        <ReferenceLine
          x={now}
          stroke={colors.now}
          strokeWidth={1.5}
          label={{
            value: "jetzt",
            position: "insideTopRight",
            fill: colors.now,
            fontSize: 11,
          }}
        />

        {visible.map((m) => (
          <Line
            key={m.key}
            type="monotone"
            dataKey={m.key}
            name={m.label}
            stroke={m.color(colors)}
            strokeWidth={m.width}
            strokeDasharray={m.dash}
            dot={false}
            activeDot={{ r: 3.5 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}

        {selLeft != null && selRight != null && (
          <ReferenceArea
            x1={selLeft}
            x2={selRight}
            fill={colors.now}
            fillOpacity={0.1}
            stroke={colors.now}
            strokeOpacity={0.3}
          />
        )}

        {/* Angeklickte Ablese-Linie: senkrechte Fuehrung + Wert je Serie. */}
        {pinned != null && (
          <ReferenceLine
            x={pinned}
            stroke={colors.axis}
            strokeWidth={1}
            ifOverflow="hidden"
            label={{
              value: fmtTime(pinned),
              position: "insideTop",
              fill: colors.secondary,
              fontSize: 10,
            }}
          />
        )}
        {pinned != null &&
          pinVals.map(({ m, v }) => (
            <ReferenceDot
              key={m.key}
              x={pinned}
              y={v}
              r={3.5}
              fill={m.color(colors)}
              stroke={colors.tooltipBg}
              strokeWidth={1.5}
              ifOverflow="hidden"
              label={{
                value: fmtCm(v),
                position: "right",
                fill: m.color(colors),
                fontSize: 11,
                fontWeight: 600,
              }}
            />
          ))}

        <Tooltip
          isAnimationActive={false}
          content={(props) => {
            const p = props as unknown as {
              active?: boolean;
              payload?: TooltipEntry[];
              label?: number;
            };
            return (
              <ChartTooltip
                active={p.active}
                payload={p.payload}
                label={p.label}
                colors={colors}
              />
            );
          }}
        />

        {/* Übersichtsleiste über den GESAMTEN Zeitraum: Fenster verschieben und
            verbreitern, um weiter in die Zukunft reichende Vorhersagen zu sehen. */}
        <Brush
          dataKey="t"
          height={26}
          travellerWidth={8}
          gap={5}
          stroke={colors.axis}
          fill={colors.tooltipBg}
          startIndex={brushStart}
          endIndex={brushEnd}
          onChange={onBrush}
          tickFormatter={(t: number) => fmtDateShort(t)}
        />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TimeTick({
  x,
  y,
  payload,
  colors,
  dayFirst,
  labelSet,
  dense,
  narrow,
}: {
  x?: number;
  y?: number;
  payload?: { value: number };
  colors: Colors;
  dayFirst: Set<number>;
  labelSet: Set<number>;
  dense: boolean;
  narrow: boolean;
}) {
  if (x == null || y == null || !payload) return null;
  const t = payload.value;
  // Dichtes Fenster: Ticks alle 3 h, Beschriftung nur alle 6 h. Unbeschriftete
  // 3-h-Ticks nur als kurzer Strich; die Marke laenger machen.
  const labeled = labelSet.has(t);
  const tickLen = labeled ? 5 : 3;
  let line1: string | null = null;
  let line2: string | null = null;
  if (labeled) {
    if (dense) {
      // Alle 6 h: Uhrzeit, Datum nur beim ersten Label des Tages.
      line1 = fmtTime(t);
      line2 = dayFirst.has(t) ? fmtDay(t) : null;
    } else if (narrow) {
      // Schmal: Tages-Ticks -> Wochentag + Datum (Uhrzeit waere 00:00).
      line1 = fmtWeekday(t);
      line2 = fmtDateShort(t);
    } else {
      // Breit: Uhrzeit, Datum nur beim ersten Tick des Tages.
      line1 = fmtTime(t);
      line2 = dayFirst.has(t) ? fmtDay(t) : null;
    }
  }
  return (
    <g transform={`translate(${x},${y})`}>
      <line x1={0} y1={0} x2={0} y2={tickLen} stroke={colors.axis} strokeWidth={1} />
      {line1 && (
        <text textAnchor="middle" fontSize={11} fill={colors.secondary} dy={16}>
          {line1}
        </text>
      )}
      {line2 && (
        <text textAnchor="middle" fontSize={10} fill={colors.muted} dy={29}>
          {line2}
        </text>
      )}
    </g>
  );
}

interface TooltipEntry {
  dataKey: SeriesKey;
  value: number;
}

function ChartTooltip({
  active,
  payload,
  label,
  colors,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: number;
  colors: Colors;
}) {
  if (!active || !payload?.length || label == null) return null;
  const byKey = new Map(payload.map((p) => [p.dataKey, p.value]));
  return (
    <div
      style={{
        background: colors.tooltipBg,
        border: `1px solid ${colors.grid}`,
        borderRadius: 8,
        padding: "8px 10px",
        fontSize: 12,
        color: colors.ink,
        boxShadow: "0 2px 10px rgba(0,0,0,0.12)",
      }}
    >
      <div style={{ color: colors.secondary, marginBottom: 4 }}>
        {fmtDateTime(label)}
      </div>
      {SERIES.filter((m) => byKey.has(m.key)).map((m) => (
        <div
          key={m.key}
          style={{ display: "flex", alignItems: "center", gap: 6, lineHeight: 1.5 }}
        >
          <span
            style={{
              width: 14,
              height: 0,
              borderTop: `${Math.max(2, m.width)}px ${m.dash ? "dashed" : "solid"} ${m.color(colors)}`,
            }}
          />
          <span style={{ color: colors.secondary }}>{m.label.split(" (")[0]}</span>
          <span style={{ marginLeft: "auto", fontWeight: 600 }}>
            {fmtCm(byKey.get(m.key) as number)}
          </span>
        </div>
      ))}
    </div>
  );
}
