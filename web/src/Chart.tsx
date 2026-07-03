import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
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
import type { Payload, SeriesKey } from "./types";

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

const HALF_DAY = 12 * 3600 * 1000;
const DAY = 24 * 3600 * 1000;

// Offset (ms) der gesetzlichen Zeit (Europe/Berlin) gegenueber UTC zu `ms`.
function berlinOffsetMs(ms: number): number {
  const d = new Date(ms);
  const asUTC = new Date(d.toLocaleString("en-US", { timeZone: "UTC" }));
  const asBerlin = new Date(
    d.toLocaleString("en-US", { timeZone: "Europe/Berlin" }),
  );
  return asBerlin.getTime() - asUTC.getTime();
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
}: {
  data: Payload;
  colors: Colors;
}) {
  const narrow = useNarrow();
  const rows = useMemo(() => toRows(data.series), [data]);
  const present = SERIES.filter((m) => data.series[m.key]?.length);

  const refLines = REF_KEYS.map((k) => ({ k, v: data.reference_lines[k] })).filter(
    (r) => typeof r.v === "number",
  );

  const { xDomain, yDomain, ticks, dayFirst } = useMemo(() => {
    const xs = rows.map((r) => r.t);
    const xMin = xs[0] ?? 0;
    const xMax = xs[xs.length - 1] ?? 0;
    let lo = Infinity;
    let hi = -Infinity;
    for (const r of rows)
      for (const m of present) {
        const v = r[m.key];
        if (typeof v === "number") {
          lo = Math.min(lo, v);
          hi = Math.max(hi, v);
        }
      }
    for (const r of refLines) {
      lo = Math.min(lo, r.v as number);
      hi = Math.max(hi, r.v as number);
    }
    const pad = 20;
    const yLo = Math.floor((lo - pad) / 20) * 20;
    const yHi = Math.ceil((hi + pad) / 20) * 20;

    const tk = makeTicks(xMin, xMax, narrow ? DAY : HALF_DAY);
    // Datumszeile nur beim ersten Tick eines Tages zeigen (wie BSH).
    const firsts = new Set<number>();
    let prevDay = "";
    for (const t of tk) {
      const d = fmtDay(t);
      if (d !== prevDay) {
        firsts.add(t);
        prevDay = d;
      }
    }
    return {
      xDomain: [xMin, xMax] as [number, number],
      yDomain: [yLo, yHi] as [number, number],
      ticks: tk,
      dayFirst: firsts,
    };
  }, [rows, present, refLines, narrow]);

  const now = Date.parse(data.now);
  const fcStart = Date.parse(data.forecast_start);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 16, right: 16, bottom: 8, left: 4 }}>
        <CartesianGrid stroke={colors.grid} vertical={false} />
        <XAxis
          type="number"
          dataKey="t"
          scale="time"
          domain={xDomain}
          ticks={ticks}
          tickLine={false}
          axisLine={{ stroke: colors.axis }}
          tick={(props) => (
            <TimeTick
              {...props}
              colors={colors}
              dayFirst={dayFirst}
              narrow={narrow}
            />
          )}
          height={40}
          interval={0}
        />
        <YAxis
          type="number"
          domain={yDomain}
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
            ifOverflow="extendDomain"
            label={{
              value: `${r.k} ${Math.round(r.v as number)}`,
              position: "insideTopLeft",
              fill: colors.muted,
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

        {present.map((m) => (
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
      </LineChart>
    </ResponsiveContainer>
  );
}

function TimeTick({
  x,
  y,
  payload,
  colors,
  dayFirst,
  narrow,
}: {
  x?: number;
  y?: number;
  payload?: { value: number };
  colors: Colors;
  dayFirst: Set<number>;
  narrow: boolean;
}) {
  if (x == null || y == null || !payload) return null;
  const t = payload.value;
  // Schmal: Tages-Ticks -> Wochentag + Datum (Uhrzeit waere 00:00, redundant).
  // Breit: 12-h-Ticks -> Uhrzeit, Datum nur beim ersten Tick des Tages.
  const line1 = narrow ? fmtWeekday(t) : fmtTime(t);
  const line2 = narrow ? fmtDateShort(t) : dayFirst.has(t) ? fmtDay(t) : null;
  return (
    <g transform={`translate(${x},${y})`}>
      <text textAnchor="middle" fontSize={11} fill={colors.secondary} dy={12}>
        {line1}
      </text>
      {line2 && (
        <text textAnchor="middle" fontSize={10} fill={colors.muted} dy={26}>
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
