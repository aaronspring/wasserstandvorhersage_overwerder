#!/usr/bin/env python3
"""Ueberflutungs-Zeitpunkte fuer Overhaken / Overwerder aus DGM1 + Wasserstand.

Laedt (einmalig, gecacht) die DGM1-Kacheln des LGV Hamburg, berechnet je
1-m-Zelle die Ueberlaufhoehe vom Strom aus und daraus fuer eine
Wasserstandskurve am Pegel Over: Beginn, Ende, nasse Dauer und maximale Tiefe.
Ergebnis: GeoTIFFs, eine Tabelle Gelaendehoehe -> Zeitpunkt und eine Grafik.

    uv sync --extra gelaende
    python inundation.py --data web/public/data.json        # aktuelle Vorhersage
    python inundation.py --recent                           # hoechste Tide, 31 Tage
    python inundation.py --event 2013-12-06                 # Xaver (PEGELONLINE-Archiv)
    python inundation.py --demo --peak-cm 960               # synthetische Sturmflut
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from wasserstand_overwerder import config, inundation


def level_from_data_json(path: str) -> tuple[pd.Series, float]:
    """Over-Messung + Overwerder-Vorhersage aus data.json (cm ueber PNP)."""
    d = json.loads(Path(path).read_text())

    def series(key: str) -> pd.Series:
        pairs = d["series"].get(key, [])
        return pd.Series(
            [v for _, v in pairs], index=pd.to_datetime([t for t, _ in pairs], utc=True)
        )

    obs, fc = series("over"), series("overwerder")
    w = pd.concat([obs, fc[fc.index > obs.index.max()] if len(obs) else fc])
    return w, d.get("gauge_zero_m_nhn") or config.OVER_PNP_NHN_M


def level_from_event(day: str) -> pd.Series:
    """Minuetliche Over-Rohdaten von Vortag bis 2 Tage danach (Archiv)."""
    from wasserstand_overwerder import history

    t = pd.Timestamp(day, tz="UTC")
    w = history.fetch_history(
        "over", t - pd.Timedelta(days=1), t + pd.Timedelta(days=2)
    )
    return w.resample("5min").mean().dropna()


def level_recent() -> pd.Series:
    """Over-Messung der letzten 31 Tage (PEGELONLINE-REST), 5-min-Mittel."""
    from wasserstand_overwerder import pegelonline

    return pegelonline.observations("over", "P31D").resample("5min").mean().dropna()


def demo_level(peak_cm: float) -> pd.Series:
    """Zwei M2-Tiden um MThw ~ 760 cm, mittlere mit Windstau bis ``peak_cm``."""
    idx = pd.date_range("2026-01-01", periods=36 * 12, freq="5min", tz="UTC")
    hrs = (idx - idx[0]).total_seconds() / 3600.0
    tide = 600.0 + 160.0 * np.cos(2 * np.pi * (hrs - 18.0) / 12.42)
    surge = (peak_cm - 760.0) * np.exp(-(((hrs - 18.0) / 5.0) ** 2))
    return pd.Series(tide + surge, index=idx)


def area_mask(terrain: inundation.Terrain, bbox) -> np.ndarray:
    """Bool-Raster: Zellmittelpunkte innerhalb ``bbox`` (EPSG:25832)."""
    t = terrain.transform
    h, w = terrain.z.shape
    x = t.c + (np.arange(w) + 0.5) * t.a
    y = t.f + (np.arange(h) + 0.5) * t.e
    xmin, ymin, xmax, ymax = bbox
    return ((y >= ymin) & (y <= ymax))[:, None] & ((x >= xmin) & (x <= xmax))[None, :]


def plot(terrain, timing, level_m, tide, table, peak, area_bbox, out: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rel_min = (
        timing["onset"] - peak.tz_localize(None).to_datetime64()
    ) / np.timedelta64(1, "m")
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), width_ratios=[1.2, 1, 1])
    ax = axes[0]
    ax.imshow(terrain.z, cmap="gray", vmin=0, vmax=9, extent=terrain.extent)
    im = ax.imshow(
        rel_min, cmap="viridis", vmin=np.nanmin(rel_min), vmax=0, extent=terrain.extent
    )
    fig.colorbar(im, ax=ax, shrink=0.8, label="Beginn relativ zum Scheitel [min]")
    xmin, ymin, xmax, ymax = area_bbox
    ax.plot([xmin, xmax, xmax, xmin, xmin], [ymin, ymin, ymax, ymax, ymin], "r--", lw=1)
    ax.set_title("Ueberflutungsbeginn in der Sturmtide (DGM1 2022)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=7)

    ax = axes[1]
    win = pd.Timedelta(hours=18)
    loc = level_m[peak - win : peak + win].tz_convert("Europe/Berlin")
    ax.plot(loc.index, loc.values, color="#1f77b4")
    ax.axvspan(tide.index[0], tide.index[-1], color="C1", alpha=0.1, label="Sturmtide")
    ax.legend(loc="upper right", fontsize=8)
    for zc in np.arange(2.5, 4.51, 0.5):
        ax.axhline(zc, color="0.6", lw=0.6, ls=":")
        ax.text(loc.index[0], zc, f" {zc:.1f} m", fontsize=7, va="bottom", color="0.4")
    ax.set_ylabel("Wasserstand Over [m NHN]")
    ax.set_title("Wasserstand und Gelaendehoehen")
    fig.autofmt_xdate()

    ax = axes[2]
    tab = table[table["cells"] >= 50]
    rel = (tab["onset_median"] - peak).dt.total_seconds() / 60.0
    ax.plot(tab.index, rel, "o-", label="Beginn - Scheitel [min]")
    ax.plot(tab.index, tab["hours_wet_median"] * 60.0, "s-", label="nasse Dauer [min]")
    ax.axhline(0, color="k", lw=0.5)
    ax.set_xlabel("Gelaendehoehe [m NHN] (0,1-m-Klassen, Auswerteflaeche)")
    ax.set_ylabel("Minuten")
    ax2 = ax.twinx()
    ax2.bar(tab.index, tab["wet_share"], width=0.08, alpha=0.2, color="C2")
    ax2.set_ylabel("Anteil nass", color="C2")
    ax2.set_ylim(0, 1.05)
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlim(1.5, max(5.0, float(tab.index.max()) + 0.2))
    ax.set_title("Wie die Gelaendehoehe den Zeitpunkt steuert")
    fig.text(
        0.99,
        0.01,
        "Gelaende: DGM1 (c) LGV Hamburg, dl-de/by-2-0",
        ha="right",
        fontsize=7,
    )
    fig.tight_layout()
    p = out / "inundation.png"
    fig.savefig(p, dpi=110)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--data", help="data.json aus export_web.py (Messung+Vorhersage)")
    src.add_argument("--event", help="Tag einer Sturmflut, z. B. 2013-12-06 (Archiv)")
    src.add_argument(
        "--recent", action="store_true", help="hoechste Tide der letzten 31 Tage"
    )
    src.add_argument("--demo", action="store_true", help="synthetische Sturmflut")
    ap.add_argument("--peak-cm", type=float, default=960.0, help="Scheitel fuer --demo")
    ap.add_argument(
        "--gauge-zero", type=float, default=None, help="PNP Over in m NHN (Override)"
    )
    ap.add_argument(
        "--tiles", default="out/dgm1", help="Cache-Verzeichnis DGM1-Kacheln"
    )
    ap.add_argument("--out", default="out/inundation", help="Ausgabeverzeichnis")
    ap.add_argument(
        "--area-bbox",
        type=float,
        nargs=4,
        default=config.OVERHAKEN_BBOX,
        metavar=("XMIN", "YMIN", "XMAX", "YMAX"),
        help="Auswerteflaeche (EPSG:25832)",
    )
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    gauge_zero = config.OVER_PNP_NHN_M
    if args.data:
        w, gauge_zero = level_from_data_json(args.data)
    elif args.event:
        w = level_from_event(args.event)
    elif args.recent:
        w = level_recent()
    else:
        w = demo_level(args.peak_cm)
    if args.gauge_zero is not None:
        gauge_zero = args.gauge_zero
    level = inundation.cm_pnp_to_m_nhn(w, gauge_zero)
    peak = level.idxmax()
    # Sturmtide: vom Tnw vor dem Scheitel bis zum Tnw danach. Zellen, die schon
    # bei frueheren Tiden nass waren, bekommen so trotzdem einen Beginn relativ
    # zum Sturmflut-Scheitel.
    half = pd.Timedelta(hours=9)
    tide = level[
        level[peak - half : peak].idxmin() : level[peak : peak + half].idxmin()
    ]
    print(
        f"Wasserstand: {len(level)} Werte, Scheitel {level.max():.2f} m NHN "
        f"({w.max():.0f} cm PNP, PNP={gauge_zero:+.3f} m NHN) am "
        f"{peak.tz_convert('Europe/Berlin'):%d.%m.%Y %H:%M}"
    )

    print("DGM1-Kacheln ...")
    paths = inundation.fetch_tiles(config.INUNDATION_BBOX, args.tiles)
    terrain = inundation.load_terrain(paths, config.INUNDATION_BBOX)
    river = inundation.river_mask(terrain.z)
    spill = inundation.spill_elevation(terrain.z, river)
    timing = inundation.flood_timing(spill, terrain.z, tide)

    area = area_mask(terrain, args.area_bbox) & (spill < config.VORLAND_MAX_SPILL_M)
    table = inundation.height_timing_table(terrain.z, timing, area)
    table.to_csv(out / "hoehe_zeitpunkt.csv")

    rel_min = (
        timing["onset"] - peak.tz_localize(None).to_datetime64()
    ) / np.timedelta64(1, "m")
    for name, data in {
        "spill_m_nhn": spill,
        "onset_min_rel_peak": rel_min,
        "hours_wet": timing["hours_wet"],
        "max_depth_m": timing["max_depth"],
    }.items():
        inundation.write_geotiff(out / f"{name}.tif", terrain, data)

    wet = area & np.isfinite(timing["hours_wet"])
    print(
        f"Auswerteflaeche: {area.sum() / 1e4:.1f} ha, "
        f"davon nass {wet.sum() / 1e4:.1f} ha ({wet.sum() / max(area.sum(), 1):.0%})"
    )
    if wet.any():
        first = pd.Timestamp(np.nanmin(timing["onset"][wet])).tz_localize("UTC")
        print(f"erste nasse Zelle: {first.tz_convert('Europe/Berlin'):%d.%m. %H:%M}")
    print(f"-> {plot(terrain, timing, level, tide, table, peak, args.area_bbox, out)}")
    print(f"-> {out}/hoehe_zeitpunkt.csv, *.tif")


if __name__ == "__main__":
    main()
