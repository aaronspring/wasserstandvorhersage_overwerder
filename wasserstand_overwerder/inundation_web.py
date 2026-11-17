"""Statisches Gelaende-Asset fuer die Overhaken-Karte der Web-App (netzfrei).

Die Web-App rechnet die Wassertiefe zum Hover-Zeitpunkt selbst (wie
``inundation.depth_at``): Zelle nass, sobald das laufende Maximum des
Wasserstands ihre Ueberlaufhoehe erreicht; Spiegel = max(Wasserstand,
Ueberlaufhoehe - Versickerung seit dem letzten Kontakt), Tiefe = Spiegel -
Gelaende. Dafuer braucht sie nur Gelaende,
Ueberlaufhoehe, Klassen (Land/Elbe/sonstiges Wasser), eine Schummerung und die
Gebaeude - alles zeitunabhaengig, daher einmal erzeugt und eingecheckt.

Raster: zeilenweise von Nord nach Sued, Int16 (cm NHN, ``NODATA`` = keine
Angabe) bzw. Uint8, little-endian, base64.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .inundation import Terrain, travel_distance

NODATA = -32768
LAND, RIVER, OTHER_WATER = 0, 1, 2


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


def _cm(a: np.ndarray) -> np.ndarray:
    out = np.round(a * 100.0)
    return np.where(np.isfinite(out), out, NODATA).astype("<i2")


def hillshade(z: np.ndarray, cell_m: float, azimuth=315.0, altitude=35.0, exag=4.0):
    """Schummerung 0..255 (Licht aus NW), NaN als flach behandelt."""
    zf = np.where(np.isfinite(z), z, np.nanmedian(z)) * exag
    dy, dx = np.gradient(zf, cell_m)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)  # Zeilen laufen nach Sueden
    az, alt = np.radians(360.0 - azimuth + 90.0), np.radians(altitude)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(
        az - aspect
    )
    return np.clip(shade * 255.0, 0, 255).astype("u1")


def build_asset(
    terrain: Terrain,
    river: np.ndarray,
    spill: np.ndarray,
    view: tuple[float, float, float, float],
    *,
    step: int = 2,
    gauge_zero_m_nhn: float,
    drain_m_per_h: float = 0.0,
    flow_m_s: float | None = None,
    margin_m: float = 300.0,
    area_bbox: tuple[float, float, float, float] | None = None,
    bldg: pd.DataFrame | None = None,
    labels: tuple = (),
) -> dict:
    """Asset-Dict fuer ``view`` (EPSG:25832), jede ``step``-te Zelle."""
    t = terrain.transform
    xmin, ymin, xmax, ymax = view
    c0, c1 = int((xmin - t.c) / t.a), int((xmax - t.c) / t.a)
    r0, r1 = int((ymax - t.f) / t.e), int((ymin - t.f) / t.e)
    sl = (slice(r0, r1, step), slice(c0, c1, step))
    z, rv, sp = terrain.z[sl], river[sl], spill[sl]
    lag_min = None
    if flow_m_s:
        # Fliessweg auf einem um margin_m erweiterten Ausschnitt, damit Wege
        # von ausserhalb des Kartenausschnitts mitzaehlen; dann zuschneiden.
        # Rand je Seite als Vielfaches von step, damit das grobe Raster
        # phasengleich zu z bleibt (auch wenn der Rand am Modellrand endet).
        m = int(margin_m / abs(t.a))
        mr, mc = min(m, r0) // step * step, min(m, c0) // step * step
        R0, C0 = r0 - mr, c0 - mc
        big = (slice(R0, r1 + m, step), slice(C0, c1 + m, step))
        dist = travel_distance(spill[big], river[big], abs(t.a) * step)
        i0, j0 = mr // step, mc // step
        dist = dist[i0 : i0 + z.shape[0], j0 : j0 + z.shape[1]]
        lag = np.nan_to_num(dist / flow_m_s / 60.0, nan=0.0)
        lag_min = np.clip(np.round(lag), 0, 255).astype("u1")
    cls = np.where(rv, RIVER, np.where(np.isfinite(z), LAND, OTHER_WATER)).astype("u1")
    cell = abs(t.a) * step
    h, w = z.shape
    ext = [t.c + c0 * t.a, t.f + r0 * t.e - h * cell, t.c + c0 * t.a + w * cell]
    ext.append(t.f + r0 * t.e)  # [xmin, ymin, xmax, ymax] der Rasterkanten

    asset: dict = {
        "crs": "EPSG:25832",
        "extent": [round(v, 2) for v in ext],
        "cell_m": cell,
        "width": w,
        "height": h,
        "gauge_zero_m_nhn": gauge_zero_m_nhn,
        "drain_m_per_h": drain_m_per_h,
        "flow_m_s": flow_m_s,
        "lag_min": _b64(lag_min) if lag_min is not None else None,
        "nodata": NODATA,
        "z_cm": _b64(_cm(z)),
        "spill_cm": _b64(_cm(sp)),
        "cls": _b64(cls),
        "shade": _b64(hillshade(z, cell)),
        "area": list(area_bbox) if area_bbox else None,
        "photo": None,
        "labels": [
            [txt, round(x - ext[0], 1), round(y - ext[1], 1)] for txt, x, y in labels
        ],
        "buildings": [],
    }
    if bldg is not None:
        for r in bldg.itertuples():
            fp = np.asarray(r.footprint, dtype=float)
            asset["buildings"].append(
                {
                    "nr": int(r.nr),
                    "alkis_id": r.alkis_id,
                    "address": r.address or "",
                    "base_m": round(float(r.base_m), 2),
                    "spill_m": (
                        round(float(r.spill_m), 2) if np.isfinite(r.spill_m) else None
                    ),
                    "ring": np.round(fp - [ext[0], ext[1]], 1).tolist(),
                }
            )
    return asset


def dop_url(view, year: int, m_per_px: float = 0.5) -> str:
    """WMS-GetMap-URL fuer das Luftbild (JPEG) passend zu ``view``."""
    from urllib.parse import urlencode

    from .config import DOP_WMS_LAYER, DOP_WMS_URL

    xmin, ymin, xmax, ymax = view
    q = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": DOP_WMS_LAYER,
        "STYLES": "",
        "CRS": "EPSG:25832",
        "BBOX": f"{xmin},{ymin},{xmax},{ymax}",
        "WIDTH": round((xmax - xmin) / m_per_px),
        "HEIGHT": round((ymax - ymin) / m_per_px),
        "FORMAT": "image/jpeg",
        "TIME": str(year),
    }
    return f"{DOP_WMS_URL}?{urlencode(q)}"


def fetch_dop(path: str | Path, view, year: int) -> Path:
    """Luftbild fuer ``view`` als JPEG speichern (braucht Netz)."""
    import urllib.request

    p = Path(path)
    with urllib.request.urlopen(dop_url(view, year), timeout=60) as r:
        if not r.headers.get("Content-Type", "").startswith("image/"):
            raise RuntimeError(f"WMS lieferte kein Bild: {r.read(300)!r}")
        p.write_bytes(r.read())
    return p


def write_asset(path: str | Path, asset: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asset, separators=(",", ":")))
    return p


def decode(asset: dict, key: str) -> np.ndarray:
    """Raster aus dem Asset zurueck (fuer Tests/Pruefung)."""
    dtype = "u1" if key in ("cls", "shade", "lag_min") else "<i2"
    a = np.frombuffer(base64.b64decode(asset[key]), dtype=dtype)
    return a.reshape(asset["height"], asset["width"])
