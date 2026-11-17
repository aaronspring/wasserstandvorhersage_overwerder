#!/usr/bin/env python3
"""Ueberflutungs-Zeitpunkte fuer Overhaken / Overwerder aus DGM1 + Wasserstand.

Laedt (einmalig, gecacht) die DGM1-Kacheln des LGV Hamburg, berechnet je
1-m-Zelle die Ueberlaufhoehe vom Strom aus und daraus fuer eine
Wasserstandskurve am Pegel Over: Beginn, Ende, nasse Dauer und maximale Tiefe.
Beim Ablauf bleibt Stauwasser in Senken hinter Sommerdeichen bis zur
Ueberlaufhoehe stehen (``--drain-cm-h`` laesst es sinken). Ergebnis:
GeoTIFFs, eine Tabelle Gelaendehoehe -> Zeitpunkt und Grafiken (Uebersicht,
Gelaendekarte, Querprofil, Verlauf; mit ``--animate`` zusaetzlich ein GIF).

    uv sync --extra gelaende
    python inundation.py --data web/public/data.json        # aktuelle Vorhersage
    python inundation.py --recent --animate                 # hoechste Tide, 31 Tage
    python inundation.py --event 2013-12-06                 # Xaver (PEGELONLINE-Archiv)
    python inundation.py --demo --peak-cm 960               # synthetische Sturmflut
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from wasserstand_overwerder import (
    buildings,
    config,
    inundation,
    inundation_plot,
    inundation_web,
)


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
    ap.add_argument("--lod2", default="out/lod2", help="Cache LoD2-Gebaeudekacheln")
    ap.add_argument(
        "--no-buildings", action="store_true", help="ohne Gebaeude (kein LoD2-Download)"
    )
    ap.add_argument("--out", default="out/inundation", help="Ausgabeverzeichnis")
    ap.add_argument(
        "--drain-cm-h",
        type=float,
        default=config.INUNDATION_DRAIN_M_PER_H * 100.0,
        help="Ablauf von Stauwasser aus Senken in cm/h (Default 0: bleibt stehen)",
    )
    ap.add_argument("--animate", action="store_true", help="zusaetzlich animation.gif")
    ap.add_argument(
        "--web-asset",
        default=None,
        help="Gelaende-Asset fuer die Web-Karte (web/public/overhaken.json)",
    )
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
    drain = args.drain_cm_h / 100.0
    timing = inundation.flood_timing(spill, terrain.z, tide, drain)

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
        "residual_depth_m": timing["residual_depth"],
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
    pond = timing["residual_depth"][area & (timing["residual_depth"] > 0)]
    print(
        f"Stauwasser am Ende der Sturmtide: {pond.size / 1e4:.1f} ha, "
        f"Median {np.median(pond) if pond.size else 0:.2f} m, "
        f"Max {pond.max() if pond.size else 0:.2f} m (Ablauf {args.drain_cm_h:g} cm/h)"
    )

    bldg = None
    if not args.no_buildings:
        print("LoD2-Gebaeude ...")
        bldg = buildings.parse_lod2(
            buildings.fetch_lod2(config.INUNDATION_VIEW, args.lod2)
        )
        bldg = buildings.flood_table(
            buildings.select(bldg, args.area_bbox),
            terrain,
            spill,
            timing,
            float(tide.max()),
        )
        bldg = buildings.number_buildings(
            bldg[bldg["spill_m"] < config.VORLAND_MAX_SPILL_M]
        )
        csv = bldg.drop(columns=["footprint"]).assign(
            onset=bldg["onset"].dt.tz_convert("Europe/Berlin"),
            onset_min_rel_peak=(bldg["onset"] - peak).dt.total_seconds() / 60.0,
        )
        csv.to_csv(out / "gebaeude.csv", index=False, float_format="%.3f")
        reached = bldg["onset"].notna()
        print(
            f"Gebaeude im Vorland: {len(bldg)}, davon {reached.sum()} vom Wasser "
            f"erreicht, {(bldg['depth_m'] > 0).sum()} mit Wasser ueber Bodenhoehe; "
            f"{(bldg['number'] != '').sum()} mit ALKIS-Hausnummer"
        )

    if args.web_asset:
        asset = inundation_web.build_asset(
            terrain,
            river,
            spill,
            config.INUNDATION_VIEW,
            gauge_zero_m_nhn=config.OVER_PNP_NHN_M,
            area_bbox=args.area_bbox,
            bldg=bldg,
            labels=config.INUNDATION_MAP_LABELS,
        )
        p = inundation_web.write_asset(args.web_asset, asset)
        print(f"-> {p} ({p.stat().st_size / 1e3:.0f} kB)")

    gelaende_m = config.WASSER_AUF_GELAENDE_OVER_CM / 100.0 + gauge_zero
    plots = [
        inundation_plot.summary(
            terrain, timing, level, tide, table, peak, args.area_bbox, out
        ),
        inundation_plot.terrain_map(
            terrain, river, spill, args.area_bbox, gelaende_m, out, bldg
        ),
        inundation_plot.profile(
            terrain, river, spill, level, tide, peak, gelaende_m, drain, out, bldg
        ),
        inundation_plot.snapshots(terrain, river, spill, tide, peak, drain, out, bldg),
    ]
    if bldg is not None:
        plots.append(inundation_plot.buildings_map(terrain, river, bldg, peak, out))
    if args.animate:
        plots.append(
            inundation_plot.animation(
                terrain, river, spill, tide, gelaende_m, drain, out, bldg
            )
        )
    for p in plots:
        print(f"-> {p}")
    print(f"-> {out}/hoehe_zeitpunkt.csv, gebaeude.csv, *.tif")


if __name__ == "__main__":
    main()
