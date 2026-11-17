#!/usr/bin/env python3
"""Gelaende-Asset fuer die Overhaken-Karte der Web-App erzeugen.

Laedt (einmalig, gecacht) die DGM1-Kacheln und LoD2-Gebaeude des LGV Hamburg,
berechnet je Rasterzelle Ueberlaufhoehe und Fliessweg vom Strom und schreibt
das statische Asset ``web/public/overhaken.json`` plus das Luftbild
``web/public/overhaken_dop.jpg``. Die Web-App rechnet daraus die Wassertiefe
fuer jeden Zeitpunkt selbst; noetig ist ein neuer Lauf nur, wenn sich
Ausschnitt oder Parameter in ``config.py`` aendern.

    uv sync --extra gelaende
    uv run python inundation.py
"""

import argparse
from pathlib import Path

from wasserstand_overwerder import buildings, config, inundation, inundation_web


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="web/public", help="Zielverzeichnis")
    ap.add_argument("--tiles", default="out/dgm1", help="Cache DGM1-Kacheln")
    ap.add_argument("--lod2", default="out/lod2", help="Cache LoD2-Kacheln")
    ap.add_argument("--no-photo", action="store_true", help="kein Luftbild laden (WMS)")
    args = ap.parse_args()
    out = Path(args.out)

    print("DGM1-Kacheln ...")
    terrain = inundation.load_terrain(
        inundation.fetch_tiles(config.INUNDATION_BBOX, args.tiles),
        config.INUNDATION_BBOX,
    )
    river = inundation.river_mask(terrain.z)
    spill = inundation.spill_elevation(terrain.z, river)

    print("LoD2-Gebaeude ...")
    bldg = buildings.parse_lod2(buildings.fetch_lod2(config.INUNDATION_VIEW, args.lod2))
    bldg = buildings.add_spill(
        buildings.select(bldg, config.OVERHAKEN_BBOX), terrain, spill
    )
    bldg = buildings.number_buildings(
        bldg[bldg["spill_m"] < config.VORLAND_MAX_SPILL_M]
    )
    print(f"  {len(bldg)} Gebaeude in der Kolonie")

    print("Fliessweg + Asset ...")
    asset = inundation_web.build_asset(
        terrain,
        river,
        spill,
        config.INUNDATION_VIEW,
        gauge_zero_m_nhn=config.OVER_PNP_NHN_M,
        drain_m_per_h=config.INUNDATION_DRAIN_M_PER_H,
        flow_m_s=config.INUNDATION_FLOW_M_S,
        area_bbox=config.OVERHAKEN_BBOX,
        bldg=bldg,
        labels=config.INUNDATION_MAP_LABELS,
    )
    if not args.no_photo:
        photo = out / "overhaken_dop.jpg"
        try:
            inundation_web.fetch_dop(photo, config.INUNDATION_VIEW, config.DOP_YEAR)
            asset["photo"] = {
                "file": photo.name,
                "credit": f"Luftbild DOP {config.DOP_YEAR} (c) LGV, dl-de/by-2.0",
            }
            print(f"-> {photo}")
        except Exception as e:  # Luftbild ist optional
            print(f"Hinweis: Luftbild nicht geladen ({e})")
    p = inundation_web.write_asset(out / "overhaken.json", asset)
    print(f"-> {p} ({p.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
