"""Gebaeude aus dem 3D-Gebaeudemodell LoD2-DE Hamburg (LGV) fuer die
Overhaken-Karte: Grundriss, Bodenhoehe, Hausnummer und je Gebaeude die
Ueberlaufhoehe, ab der Wasser es erreicht.

Quelle: CityGML-Kacheln 1x1 km (``LoD2_32_<E km>_<N km>_1_HH.gml``) im
Hamburg-ZIP, per HTTP-Range geladen wie das DGM1. Datenlizenz Deutschland -
Namensnennung 2.0, (c) LGV Hamburg.

**Nummern:** ALKIS fuehrt fuer die meisten Lauben/Wochenendhaeuser im
Overwerder Vorland **keine Hausnummer**. Jedes Gebaeude bekommt deshalb eine
laufende Nummer (entlang des Deichs von NW nach SO), und wo ALKIS eine
Adresse hat, steht sie in ``address``. Die ALKIS-Kennung (``alkis_id``)
bleibt fuer den Abgleich erhalten.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

from .config import LOD2_URL
from .inundation import Terrain, fetch_tiles

NS = {
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml": "http://www.opengis.net/gml",
    "xAL": "urn:oasis:names:tc:ciq:xsdschema:xAL:2.0",
}
FUNCTION = {
    "31001_1010": "Wohnhaus",
    "31001_1310": "Freizeitgebaeude",
    "31001_1313": "Gartenhaus",
}


def fetch_lod2(bbox, out_dir: str | Path, url: str = LOD2_URL) -> list[Path]:
    """LoD2-Kacheln fuer ``bbox`` (EPSG:25832) nach ``out_dir`` laden."""
    return fetch_tiles(bbox, out_dir, url, pattern="LoD2_32_{e}_{n}_1_HH.gml")


def _ring(pos: str) -> np.ndarray:
    return np.array(pos.split(), dtype=float).reshape(-1, 3)


def parse_lod2(paths: list[Path]) -> pd.DataFrame:
    """Ein Datensatz je Gebaeude: ``alkis_id``, ``function``, ``street``,
    ``number``, ``base_m`` (Bodenhoehe m NHN, tiefster Punkt der
    Grundflaeche), ``height_m``, ``footprint`` (Nx2, EPSG:25832), ``x``/``y``
    (Schwerpunkt)."""
    rows = []
    for p in paths:
        for b in ET.parse(p).getroot().iter(f"{{{NS['bldg']}}}Building"):
            rings = [
                _ring(e.text)
                for e in b.iterfind(".//bldg:GroundSurface//gml:posList", NS)
            ]
            if not rings:
                continue
            fp = max(rings, key=len)
            base = min(r[:, 2].min() for r in rings)
            street = b.findtext(".//xAL:ThoroughfareName", "", NS).strip()
            number = b.findtext(".//xAL:ThoroughfareNumber", "", NS).strip()
            height = b.findtext("bldg:measuredHeight", "nan", NS)
            rows.append(
                {
                    "alkis_id": b.get("{http://www.opengis.net/gml}id"),
                    "function": b.findtext("bldg:function", "", NS),
                    "street": street,
                    "number": number,
                    "base_m": float(base),
                    "height_m": float(height),
                    "footprint": fp[:, :2],
                    "x": float(fp[:, 0].mean()),
                    "y": float(fp[:, 1].mean()),
                }
            )
    df = pd.DataFrame(rows).drop_duplicates("alkis_id")
    df["kind"] = df["function"].map(FUNCTION).fillna("sonstiges")
    df["address"] = (df["street"] + " " + df["number"]).str.strip()
    return df.reset_index(drop=True)


def number_buildings(df: pd.DataFrame, axis=(0.62, -0.78)) -> pd.DataFrame:
    """Laufende Nummer ``nr`` 1..n entlang ``axis`` (Einheitsvektor; Default
    parallel zum Overwerder Hauptdeich von NW nach SO)."""
    order = np.argsort(df["x"] * axis[0] + df["y"] * axis[1], kind="stable")
    out = df.iloc[order].reset_index(drop=True)
    out.insert(0, "nr", np.arange(1, len(out) + 1))
    return out


def label_parzellen(df: pd.DataFrame, parzellen: dict[str, str]) -> pd.DataFrame:
    """Nur Gebaeude mit Parzellen-Nummer behalten, Spalte ``parzelle`` setzen.

    ``parzellen`` bildet die ALKIS-Kennung auf die Nummer laut Lageplan ab
    (``config.OVERHAKEN_PARZELLEN``); eine Parzelle kann mehrere Gebaeude haben.
    """
    out = df[df["alkis_id"].isin(parzellen)].reset_index(drop=True)
    return out.assign(parzelle=out["alkis_id"].map(parzellen))


def select(df: pd.DataFrame, bbox) -> pd.DataFrame:
    """Gebaeude, deren Schwerpunkt in ``bbox`` liegt."""
    xmin, ymin, xmax, ymax = bbox
    m = df["x"].between(xmin, xmax) & df["y"].between(ymin, ymax)
    return df[m].reset_index(drop=True)


def footprint_cells(terrain: Terrain, footprint: np.ndarray) -> tuple:
    """Zeilen/Spalten der Rasterzellen, deren Mittelpunkt im Grundriss liegt
    (mindestens die Zelle unter dem Schwerpunkt)."""
    from matplotlib.path import Path as MplPath

    t = terrain.transform
    cols = (footprint[:, 0] - t.c) / t.a
    rows = (footprint[:, 1] - t.f) / t.e
    r0, r1 = int(np.floor(rows.min())), int(np.ceil(rows.max())) + 1
    c0, c1 = int(np.floor(cols.min())), int(np.ceil(cols.max())) + 1
    rr, cc = np.mgrid[r0:r1, c0:c1]
    inside = MplPath(np.c_[cols, rows]).contains_points(
        np.c_[cc.ravel() + 0.5, rr.ravel() + 0.5]
    )
    if not inside.any():
        return np.array([int(rows.mean())]), np.array([int(cols.mean())])
    return rr.ravel()[inside], cc.ravel()[inside]


def add_spill(df: pd.DataFrame, terrain: Terrain, spill: np.ndarray) -> pd.DataFrame:
    """Je Gebaeude ``spill_m``: niedrigste Ueberlaufhoehe im Grundriss (ab
    diesem Elbe-Wasserstand erreicht Wasser das Gebaeude)."""
    out = df.copy()
    spills = []
    for fp in df["footprint"]:
        r, c = footprint_cells(terrain, fp)
        sp = spill[r, c]
        spills.append(np.nanmin(sp) if np.isfinite(sp).any() else np.nan)
    out["spill_m"] = spills
    return out
