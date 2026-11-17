import { useEffect, useMemo, useRef, useState } from "react";

import { useCursor } from "./cursor";
import { fmtDateShort, fmtTime, fmtWeekday } from "./format";
import type { Payload, Point } from "./types";

// Karte der Kolonie Overhaken zum Zeitpunkt unter dem Mauszeiger im Chart
// (sonst fixierte Ablese-Linie, sonst "jetzt"). Rechnung wie
// inundation.depth_at: Zelle nass, sobald das laufende Maximum des
// Wasserstands ihre Ueberlaufhoehe erreicht; Spiegel = max(Wasserstand,
// Ueberlaufhoehe - Versickerung seit dem letzten Kontakt zum Strom), Tiefe =
// Spiegel - Gelaende. Stauwasser in Senken versickert also (Sandboden).
// Gelaende-Asset aus
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
  drain_m_per_h?: number;
  nodata: number;
  z_cm: string;
  spill_cm: string;
  cls: string;
  shade: string;
  flow_m_s?: number | null;
  lag_min?: string | null;
  photo?: { file: string; credit: string } | null;
  labels: [string, number, number][];
  buildings: Building[];
}

interface Grid {
  a: Asset;
  z: Int16Array;
  spill: Int16Array;
  cls: Uint8Array;
  shade: Uint8Array;
  lag: Uint8Array | null; // Fliesszeit vom Strom je Zelle, Minuten
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
    lag: a.lag_min ? new Uint8Array(bytes(a.lag_min)) : null,
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
interface LevelAt {
  now: number;
  max: number;
  at: number;
  lo: number; // letzter Stuetzpunkt <= at
}

function levelAt(L: Level, ms: number): LevelAt {
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
  return { now, max: Math.max(L.runMax[lo], now), at, lo };
}

// Wasserspiegel (cm NHN) einer Zelle mit Ueberlaufhoehe `spill` zum Zeitpunkt
// lv: verbunden -> Strom; sonst Schwelle minus Versickerung seit dem letzten
// Zeitpunkt, an dem der Strom die Schwelle noch erreichte. Ergebnis je
// Schwellenwert gecacht (viele Zellen teilen sich ganze cm).
function surfaceFn(L: Level, lv: LevelAt, drainCmH: number) {
  // back[k] = max(v[lo-k .. lo]): nicht fallend in k -> binaere Suche.
  const back: number[] = [];
  for (let j = lv.lo, m = -Infinity; j >= 0; j--) {
    m = Math.max(m, L.v[j]);
    back.push(m);
  }
  const cache = new Map<number, number>();
  return (spill: number): number => {
    if (lv.now >= spill || drainCmH <= 0) return Math.max(lv.now, spill);
    const hit = cache.get(spill);
    if (hit != null) return hit;
    let lo = 0;
    let hi = back.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (back[mid] >= spill) hi = mid;
      else lo = mid + 1;
    }
    const tLast = L.t[lv.lo - lo];
    const hrs = Math.max(0, (lv.at - tLast) / 3.6e6);
    const s = Math.max(lv.now, spill - drainCmH * hrs);
    cache.set(spill, s);
    return s;
  };
}

// Wasser je Fliesszeit: Eine Zelle, die `lag` Minuten Fliessweg vom Strom
// entfernt liegt, sieht den Wasserstand von vor `lag` Minuten (laufendes
// Maximum, Spiegel, Versickerung). Je Fliesszeit gecacht (ganze Minuten).
interface Water {
  max: number;
  surface: (spill: number) => number;
}

function waterFn(L: Level, when: number, drainCmH: number) {
  const cache = new Map<number, Water>();
  return (lag: number): Water => {
    let w = cache.get(lag);
    if (!w) {
      const lv = levelAt(L, when - lag * 60_000);
      w = { max: lv.max, surface: surfaceFn(L, lv, drainCmH) };
      cache.set(lag, w);
    }
    return w;
  };
}

// Erster Zeitpunkt, an dem der Wasserstand `cm` erreicht (oder null).
function firstReach(L: Level, cm: number): number | null {
  const i = L.runMax.findIndex((x) => x >= cm);
  return i < 0 ? null : L.t[i];
}

// Fliesszeit (min) am Gebaeude: Zelle unter dem Grundriss-Schwerpunkt.
function buildingLag(g: Grid, ring: [number, number][]): number {
  if (!g.lag || !ring.length) return 0;
  const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
  const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
  const col = Math.min(g.a.width - 1, Math.max(0, Math.floor(cx / g.a.cell_m)));
  const row = Math.min(g.a.height - 1, Math.max(0, g.a.height - 1 - Math.floor(cy / g.a.cell_m)));
  return g.lag[row * g.a.width + col];
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

// Kartenstile fuer den Gelaende-Hintergrund (Wasser wird immer darueber gelegt).
export type MapStyle = "hoehe" | "satellit" | "atlas";
export const MAP_STYLES: { key: MapStyle; label: string; title: string }[] = [
  { key: "hoehe", label: "Höhen", title: "Höhenstufen grün → gelb → braun, mit Schummerung" },
  { key: "satellit", label: "Satellit", title: "Luftbild (DOP, LGV Hamburg)" },
  { key: "atlas", label: "Atlas", title: "Heller Kartenstil mit 1-m-Höhenlinien" },
];
const isStyle = (v: unknown): v is MapStyle => MAP_STYLES.some((m) => m.key === v);

type Rgb = [number, number, number];

function ramp(stops: [number, Rgb][], x: number): Rgb {
  if (x <= stops[0][0]) return stops[0][1];
  for (let k = 1; k < stops.length; k++) {
    const [x1, c1] = stops[k];
    if (x <= x1) {
      const [x0, c0] = stops[k - 1];
      const f = (x - x0) / (x1 - x0);
      return [0, 1, 2].map((j) => c0[j] + f * (c1[j] - c0[j])) as Rgb;
    }
  }
  return stops[stops.length - 1][1];
}

// Hoehenstufen in cm NHN (Vorland ~1-4 m, Sommerdeich ~4-5 m, Hauptdeich ~8 m).
const HYPSO: [number, Rgb][] = [
  [0, [62, 134, 92]],
  [200, [118, 176, 104]],
  [350, [196, 214, 136]],
  [450, [232, 214, 150]],
  [600, [196, 150, 100]],
  [850, [150, 112, 84]],
];
const CONTOUR_CM = 100;

function landRgb(style: MapStyle, z: number, s: number, edge: boolean): Rgb {
  const light = s / 255;
  if (style === "atlas") {
    const k = 0.9 + 0.12 * light;
    const c: Rgb = edge ? [196, 184, 160] : [243, 239, 228];
    return [c[0] * k, c[1] * k, c[2] * k];
  }
  const base = ramp(HYPSO, z);
  const k = 0.55 + 0.6 * light;
  return [base[0] * k, base[1] * k, base[2] * k];
}

function paint(
  ctx: CanvasRenderingContext2D,
  g: Grid,
  water: (lag: number) => Water,
  dark: boolean,
  style: MapStyle,
): void {
  const { width: w, height: h, nodata } = g.a;
  const img = ctx.createImageData(w, h);
  const px = img.data;
  const atlas = style === "atlas";
  // Satellit: nur das Hochwasser auf das Luftbild legen, Rest transparent.
  const photo = style === "satellit";
  const river: number[] = atlas ? [170, 211, 223] : [120, 172, 214];
  const other: number[] = atlas ? [190, 222, 232] : [150, 190, 220];
  const dim = dark ? 0.62 : 1;
  const band = (v: number) => Math.floor(v / CONTOUR_CM);
  for (let i = 0; i < w * h; i++) {
    const o = i * 4;
    let rgb: number[];
    let alpha = 255;
    if (photo) {
      alpha = 0;
      rgb = [0, 0, 0];
      const sp = g.spill[i];
      const wa = water(g.lag ? g.lag[i] : 0);
      if (g.cls[i] === LAND && sp !== nodata && sp <= wa.max) {
        const d = wa.surface(sp) - g.z[i];
        if (d >= 1) {
          rgb = depthRgb(d);
          alpha = 200;
        }
      }
    } else if (g.cls[i] === RIVER) rgb = river;
    else if (g.cls[i] !== LAND) rgb = other;
    else {
      const s = g.shade[i];
      const z = g.z[i];
      let edge = false;
      if (atlas) {
        const r = i % w < w - 1 ? g.z[i + 1] : nodata;
        const d = i + w < w * h ? g.z[i + w] : nodata;
        edge =
          (r !== nodata && band(r) !== band(z)) || (d !== nodata && band(d) !== band(z));
      }
      rgb = landRgb(style, z, s, edge);
      const sp = g.spill[i];
      const wa = water(g.lag ? g.lag[i] : 0);
      if (sp !== nodata && sp <= wa.max) {
        const d = wa.surface(sp) - g.z[i];
        if (d >= 1) {
          const c = depthRgb(d);
          const k = 0.8;
          rgb = [0, 1, 2].map((j) => c[j] * k + rgb[j] * (1 - k));
        }
      }
    }
    px[o] = rgb[0] * dim;
    px[o + 1] = rgb[1] * dim;
    px[o + 2] = rgb[2] * dim;
    px[o + 3] = alpha;
  }
  ctx.putImageData(img, 0, 0);
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
  const [style, setStyle] = useState<MapStyle>(() => {
    try {
      const v = localStorage.getItem("overhaken-style");
      if (isStyle(v)) return v;
    } catch {
      // ohne Speicher: Standardstil
    }
    return "satellit";
  });
  const chooseStyle = (v: MapStyle) => {
    setStyle(v);
    try {
      localStorage.setItem("overhaken-style", v);
    } catch {
      // ignorieren
    }
  };

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

  // Ein Klick ins Diagramm fixiert den Zeitpunkt; Hover im Diagramm aendert ihn
  // dann nicht mehr, damit man auf der Karte in Ruhe die Tiefen abfahren kann.
  const source: "hover" | "pinned" | "now" =
    cursor.pinned != null ? "pinned" : cursor.hover != null ? "hover" : "now";
  const when = cursor.pinned ?? cursor.hover ?? clock;

  // Mauszeiger ueber der Karte: Position in % des Rahmens + Rasterzelle.
  const [probe, setProbe] = useState<{ fx: number; fy: number } | null>(null);
  const lv = level ? levelAt(level, when) : null;
  const drainCmH = (grid?.a.drain_m_per_h ?? 0) * 100;
  const water = useMemo(
    () => (level && lv ? waterFn(level, lv.at, drainCmH) : null),
    // lv ist aus level/when abgeleitet; at (ms) reicht als Abhaengigkeit.
    [level, lv?.at, drainCmH],
  );

  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || !grid || !water) return;
    paint(ctx, grid, water, dark, style);
  }, [grid, water, dark, style]);

  const bldg = useMemo(() => {
    if (!grid || !level) return [];
    return grid.a.buildings.map((b) => ({
      ...b,
      points: b.ring.map(([x, y]) => `${x},${grid.a.height * grid.a.cell_m - y}`).join(" "),
      lag: buildingLag(grid, b.ring),
      onset:
        b.spill_m == null
          ? null
          : (() => {
              const t = firstReach(level, b.spill_m * 100);
              return t == null ? null : t + buildingLag(grid, b.ring) * 60_000;
            })(),
    }));
  }, [grid, level]);

  if (missing) return null;
  if (!grid || !level || !lv || !water) {
    return <section className="map-card status">Lade Overhaken-Karte …</section>;
  }

  const a = grid.a;
  const wm = a.width * a.cell_m;
  const hm = a.height * a.cell_m;
  const gz = a.gauge_zero_m_nhn;
  const overCm = lv.now - gz * 100;
  const forecast = lv.at > level.obsEnd;
  const status = bldg.map((b) => {
    const wa = water(b.lag);
    if (b.spill_m == null || b.spill_m * 100 > wa.max) return null;
    const d = wa.surface(b.spill_m * 100) - b.base_m * 100;
    return d >= 1 ? d : null;
  });
  const label =
    source === "hover" ? "Mauszeiger" : source === "pinned" ? "fixiert" : "jetzt";

  // Wert an der Mausposition auf der Karte.
  let probeText: string[] | null = null;
  if (probe) {
    const col = Math.min(a.width - 1, Math.floor(probe.fx * a.width));
    const row = Math.min(a.height - 1, Math.floor(probe.fy * a.height));
    const i = row * a.width + col;
    const m = (cm: number) => (cm / 100).toFixed(2).replace(".", ",");
    if (grid.cls[i] === RIVER) probeText = ["Elbe / Priel"];
    else if (grid.cls[i] !== LAND) probeText = ["Gewässer"];
    else {
      const z = grid.z[i];
      const sp = grid.spill[i];
      const lag = grid.lag ? grid.lag[i] : 0;
      const wa = water(lag);
      const d = sp !== a.nodata && sp <= wa.max ? wa.surface(sp) - z : 0;
      probeText = [
        d >= 1 ? `Wassertiefe ${m(d)} m` : "trocken",
        `Gelände ${m(z)} m NHN`,
      ];
      if (grid.lag && sp !== a.nodata) probeText.push(`Fließzeit vom Strom ${lag} min`);
    }
  }

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
        <div className="map-styles" role="group" aria-label="Kartenstil">
          {MAP_STYLES.map((m) => (
            <button
              type="button"
              key={m.key}
              className={`chart-btn${style === m.key ? " on" : ""}`}
              aria-pressed={style === m.key}
              title={m.title}
              onClick={() => chooseStyle(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <dl className="map-stats">
          <div>
            <dt>Over</dt>
            <dd>
              {Math.round(overCm)} cm{" "}
              <span className="muted">({(lv.now / 100).toFixed(2).replace(".", ",")} m NHN)</span>
            </dd>
          </div>
        </dl>
      </div>
      <div
        className="map-frame"
        style={{ aspectRatio: `${wm} / ${hm}` }}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setProbe({
            fx: Math.min(Math.max((e.clientX - r.left) / r.width, 0), 0.9999),
            fy: Math.min(Math.max((e.clientY - r.top) / r.height, 0), 0.9999),
          });
        }}
        onMouseLeave={() => setProbe(null)}
      >
        {style === "satellit" && a.photo && (
          <img src={`${import.meta.env.BASE_URL}${a.photo.file}`} alt="" />
        )}
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
        {style === "satellit" && a.photo && (
          <span className="map-badge">
            Satellitenbild {a.photo.credit.match(/\d{4}/)?.[0] ?? ""}
          </span>
        )}
        {probe && probeText && (
          <div
            className={`map-probe${probe.fx > 0.6 ? " left" : ""}`}
            style={{ left: `${probe.fx * 100}%`, top: `${probe.fy * 100}%` }}
          >
            {probeText.map((t, k) => (
              <div key={k} className={k ? "muted" : undefined}>
                {t}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="map-foot">
        <span className="map-ramp" aria-hidden="true">
          {[0, 50, 100, 150, 200, 250].map((c) => (
            <i key={c} style={{ background: css(depthRgb(c)) }} />
          ))}
        </span>
        <span>Wassertiefe 0 – 2,5 m</span>
        <span className="muted">
          Mit der Maus über das Diagramm fahren; ein Klick fixiert den
          Zeitpunkt (nächster Klick löst ihn), dann zeigt die Maus auf der Karte die
          Wassertiefe. Wasser
          fließt mit {String(a.flow_m_s ?? 0).replace(".", ",")} m/s vom Strom über schon
          nasse Flächen;
          Stauwasser in Senken versickert mit {Math.round(drainCmH)} cm/h
          (Sandboden, angenommen). Gelände DGM1 (c) LGV, dl-de/by-2.0
          {style === "satellit" && a.photo ? ` · ${a.photo.credit}` : ""}.
        </span>
      </div>
    </section>
  );
}
