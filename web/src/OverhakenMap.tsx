import { useEffect, useMemo, useRef, useState } from "react";

import { useCursor } from "./cursor";
import { fmtDateShort, fmtTime, fmtWeekday } from "./format";
import type { Payload, Point } from "./types";

// Karte der Kolonie Overhaken zum Zeitpunkt unter dem Mauszeiger im Chart
// (sonst fixierte Ablese-Linie, sonst "jetzt"). Rechnung wie
// inundation.depth_at (Ablauf 0): Zelle nass, sobald das laufende Maximum des
// Wasserstands ihre Ueberlaufhoehe erreicht; Spiegel = max(Wasserstand,
// Ueberlaufhoehe), Tiefe = Spiegel - Gelaende. Gelaende-Asset aus
// `inundation.py --web-asset web/public/overhaken.json`.

const ASSET_URL = `${import.meta.env.BASE_URL}overhaken.json`;
const LAND = 0;
const RIVER = 1;
const MAX_DEPTH_CM = 250;

interface Building {
  nr: number;
  alkis_id: string;
  address: string;
  base_m: number;
  spill_m: number | null;
  ring: [number, number][];
}

interface Asset {
  extent: [number, number, number, number];
  cell_m: number;
  width: number;
  height: number;
  gauge_zero_m_nhn: number;
  nodata: number;
  z_cm: string;
  spill_cm: string;
  cls: string;
  shade: string;
  labels: [string, number, number][];
  buildings: Building[];
}

interface Grid {
  a: Asset;
  z: Int16Array;
  spill: Int16Array;
  cls: Uint8Array;
  shade: Uint8Array;
}

function bytes(b64: string): ArrayBuffer {
  const s = atob(b64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out.buffer;
}

function decode(a: Asset): Grid {
  return {
    a,
    z: new Int16Array(bytes(a.z_cm)),
    spill: new Int16Array(bytes(a.spill_cm)),
    cls: new Uint8Array(bytes(a.cls)),
    shade: new Uint8Array(bytes(a.shade)),
  };
}

// Wasserstand am Pegel (cm NHN): Over-Messung, danach Overwerder-Vorhersage.
interface Level {
  t: number[];
  v: number[]; // cm NHN
  runMax: number[];
  obsEnd: number; // letzter Messzeitpunkt (ms), -inf ohne Messung
}

function buildLevel(data: Payload, gaugeZero: number): Level | null {
  const toCm = (p: Point): [number, number] => [
    Date.parse(p[0]),
    p[1] + gaugeZero * 100,
  ];
  const obs = (data.series.over ?? []).map(toCm);
  const obsEnd = obs.length ? obs[obs.length - 1][0] : -Infinity;
  const fc = (data.series.overwerder ?? []).map(toCm).filter(([t]) => t > obsEnd);
  const all = [...obs, ...fc].sort((x, y) => x[0] - y[0]);
  if (!all.length) return null;
  const t = all.map((p) => p[0]);
  const v = all.map((p) => p[1]);
  const runMax: number[] = [];
  v.forEach((x, i) => runMax.push(i ? Math.max(runMax[i - 1], x) : x));
  return { t, v, runMax, obsEnd };
}

// Wasserstand und laufendes Maximum zum Zeitpunkt `ms` (linear interpoliert).
function levelAt(L: Level, ms: number): { now: number; max: number; at: number } {
  const n = L.t.length;
  const at = Math.min(Math.max(ms, L.t[0]), L.t[n - 1]);
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (L.t[mid] <= at) lo = mid;
    else hi = mid;
  }
  const f = L.t[hi] > L.t[lo] ? (at - L.t[lo]) / (L.t[hi] - L.t[lo]) : 0;
  const now = L.v[lo] + f * (L.v[hi] - L.v[lo]);
  return { now, max: Math.max(L.runMax[lo], now), at };
}

// Erster Zeitpunkt, an dem der Wasserstand `cm` erreicht (oder null).
function firstReach(L: Level, cm: number): number | null {
  const i = L.runMax.findIndex((x) => x >= cm);
  return i < 0 ? null : L.t[i];
}

// Blaustufen fuer 0..MAX_DEPTH_CM (hell -> dunkel).
const RAMP: [number, number, number][] = [
  [198, 225, 245],
  [107, 174, 214],
  [33, 113, 181],
  [8, 48, 107],
];
function depthRgb(cm: number): [number, number, number] {
  const x = (Math.min(Math.max(cm, 0), MAX_DEPTH_CM) / MAX_DEPTH_CM) * (RAMP.length - 1);
  const i = Math.min(Math.floor(x), RAMP.length - 2);
  const f = x - i;
  const a = RAMP[i];
  const b = RAMP[i + 1];
  return [0, 1, 2].map((k) => Math.round(a[k] + f * (b[k] - a[k]))) as [
    number,
    number,
    number,
  ];
}
const css = ([r, g, b]: [number, number, number]) => `rgb(${r},${g},${b})`;

function paint(
  ctx: CanvasRenderingContext2D,
  g: Grid,
  nowCm: number,
  maxCm: number,
  dark: boolean,
): number {
  const { width: w, height: h, nodata } = g.a;
  const img = ctx.createImageData(w, h);
  const px = img.data;
  const river = dark ? [52, 92, 128] : [169, 207, 232];
  const other = dark ? [70, 78, 86] : [196, 204, 210];
  let wet = 0;
  for (let i = 0; i < w * h; i++) {
    const o = i * 4;
    let rgb: number[];
    if (g.cls[i] === RIVER) rgb = river;
    else if (g.cls[i] !== LAND) rgb = other;
    else {
      const s = g.shade[i];
      const base = dark ? 30 + s * 0.45 : 120 + s * 0.5;
      rgb = [base, base, base * 0.98];
      const sp = g.spill[i];
      if (sp !== nodata && sp <= maxCm) {
        const d = Math.max(nowCm, sp) - g.z[i];
        if (d >= 1) {
          wet++;
          const c = depthRgb(d);
          const k = 0.82;
          rgb = [0, 1, 2].map((j) => c[j] * k + rgb[j] * (1 - k) * (s / 255 + 0.5));
        }
      }
    }
    px[o] = rgb[0];
    px[o + 1] = rgb[1];
    px[o + 2] = rgb[2];
    px[o + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return wet;
}

export default function OverhakenMap({
  data,
  dark,
}: {
  data: Payload;
  dark: boolean;
}) {
  const [grid, setGrid] = useState<Grid | null>(null);
  const [missing, setMissing] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const cursor = useCursor();

  useEffect(() => {
    fetch(ASSET_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((a: Asset) => setGrid(decode(a)))
      .catch(() => setMissing(true));
  }, []);

  const level = useMemo(
    () => (grid ? buildLevel(data, grid.a.gauge_zero_m_nhn) : null),
    [data, grid],
  );

  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setClock(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  const source: "hover" | "pinned" | "now" =
    cursor.hover != null ? "hover" : cursor.pinned != null ? "pinned" : "now";
  const when = cursor.hover ?? cursor.pinned ?? clock;
  const lv = level ? levelAt(level, when) : null;

  const [wetCells, setWetCells] = useState(0);
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || !grid || !lv) return;
    setWetCells(paint(ctx, grid, lv.now, lv.max, dark));
    // lv ist aus when/level abgeleitet; die beiden Zahlen reichen als Abhaengigkeit.
  }, [grid, lv?.now, lv?.max, dark]);

  const bldg = useMemo(() => {
    if (!grid || !level) return [];
    return grid.a.buildings.map((b) => ({
      ...b,
      points: b.ring.map(([x, y]) => `${x},${grid.a.height * grid.a.cell_m - y}`).join(" "),
      onset: b.spill_m == null ? null : firstReach(level, b.spill_m * 100),
    }));
  }, [grid, level]);

  if (missing) return null;
  if (!grid || !level || !lv) {
    return <section className="map-card status">Lade Overhaken-Karte …</section>;
  }

  const a = grid.a;
  const wm = a.width * a.cell_m;
  const hm = a.height * a.cell_m;
  const gz = a.gauge_zero_m_nhn;
  const overCm = lv.now - gz * 100;
  const forecast = lv.at > level.obsEnd;
  const status = bldg.map((b) => {
    if (b.spill_m == null || b.spill_m * 100 > lv.max) return null;
    const d = Math.max(lv.now, b.spill_m * 100) - b.base_m * 100;
    return d >= 1 ? d : null;
  });
  const nWet = status.filter((d) => d != null).length;
  const firstWet = bldg
    .map((b) => b.onset)
    .filter((t): t is number => t != null)
    .sort((x, y) => x - y)[0];
  const label =
    source === "hover" ? "Mauszeiger" : source === "pinned" ? "Ablese-Linie" : "jetzt";

  return (
    <section className="map-card">
      <div className="map-head">
        <div>
          <h2>Overhaken zum gewählten Zeitpunkt</h2>
          <p className="map-when">
            <span className={`map-src map-src-${source}`}>{label}</span>
            {fmtWeekday(lv.at)} {fmtDateShort(lv.at)} {fmtTime(lv.at)} Uhr ·{" "}
            {forecast ? "Vorhersage" : "Messung"}
          </p>
        </div>
        <dl className="map-stats">
          <div>
            <dt>Over</dt>
            <dd>
              {Math.round(overCm)} cm{" "}
              <span className="muted">({(lv.now / 100).toFixed(2).replace(".", ",")} m NHN)</span>
            </dd>
          </div>
          <div>
            <dt>Gebäude nass</dt>
            <dd>
              {nWet} von {bldg.length}
            </dd>
          </div>
          <div>
            <dt>Fläche nass</dt>
            <dd>{((wetCells * a.cell_m * a.cell_m) / 1e4).toFixed(1).replace(".", ",")} ha</dd>
          </div>
        </dl>
      </div>
      <div className="map-frame" style={{ aspectRatio: `${wm} / ${hm}` }}>
        <canvas ref={canvas} width={a.width} height={a.height} />
        <svg viewBox={`0 0 ${wm} ${hm}`} preserveAspectRatio="none">
          {bldg.map((b, i) => {
            const d = status[i];
            return (
              <polygon
                key={b.alkis_id}
                points={b.points}
                className={d == null ? "bldg dry" : "bldg wet"}
                style={d == null ? undefined : { fill: css(depthRgb(d + 60)) }}
              >
                <title>
                  {`Gebäude ${b.nr}${b.address ? ` (${b.address})` : ""}\n` +
                    `Boden ${b.base_m.toFixed(2)} m NHN\n` +
                    (d == null
                      ? "trocken"
                      : `Wasser ${Math.round(d)} cm über Boden`) +
                    (b.onset == null
                      ? "\nim Datenzeitraum nicht erreicht"
                      : `\nnass ab ${fmtDateShort(b.onset)} ${fmtTime(b.onset)} Uhr`)}
                </title>
              </polygon>
            );
          })}
          {a.labels.map(([txt, x, y]) => (
            <text key={txt} x={x} y={hm - y} className="map-label">
              {txt}
            </text>
          ))}
        </svg>
      </div>
      <div className="map-foot">
        <span className="map-ramp" aria-hidden="true">
          {[0, 50, 100, 150, 200, 250].map((c) => (
            <i key={c} style={{ background: css(depthRgb(c)) }} />
          ))}
        </span>
        <span>Wassertiefe 0 – 2,5 m</span>
        <span className="muted">
          {firstWet == null
            ? "Im Datenzeitraum erreicht das Wasser kein Gebäude."
            : `Erstes Gebäude nass: ${fmtWeekday(firstWet)} ${fmtTime(firstWet)} Uhr.`}{" "}
          Mit der Maus über das Diagramm fahren oder hineintippen. Modell:
          Gelände DGM1 (LGV), ohne Fließzeit – Wasser erscheint frühestmöglich.
        </span>
      </div>
    </section>
  );
}
