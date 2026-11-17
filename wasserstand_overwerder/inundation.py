"""Ueberflutungs-Zeitpunkt je Rasterzelle aus DGM1 (LGV Hamburg) + Wasserstand.

Badewannen-Modell mit hydraulischer Konnektivitaet: Eine Zelle wird nass,
sobald der Elbe-Wasserstand ihre **Ueberlaufhoehe** erreicht. Das ist die
niedrigste Hoehe, ueber die Wasser vom Strom aus zur Zelle gelangen kann
(Minimax-Pfad: die hoechste Schwelle auf dem guenstigsten Weg). Eine Senke
hinter einem Sommerdeich wird also erst nass, wenn der Deich ueberstroemt wird,
und das Hinterland hinter dem Hauptdeich bleibt trocken.

Die Ueberlaufhoehe haengt nur vom Gelaende ab (morphologische Rekonstruktion
durch Erosion) und wird einmal berechnet. Danach ist jede Zeitreihe billig:
Beginn = erster Zeitschritt, in dem das laufende Maximum des Wasserstands die
Ueberlaufhoehe erreicht. Beim Ablauf faellt der Spiegel einer Zelle nur bis auf
ihre Ueberlaufhoehe: Senken hinter Sommerdeichen behalten Stauwasser, das mit
einer waehlbaren Rate (Siele/Versickerung) sinkt. Fliesswiderstand und
Einstroemzeit fehlen: Der Beginn ist der fruehestmoegliche.

Gelaende: DGM1 2022 (1-m-Raster, ETRS89/UTM32 = EPSG:25832, Hoehen m ueber
NHN/DHHN2016, +/- 15 cm) aus dem Transparenzportal Hamburg; Datenlizenz
Deutschland - Namensnennung 2.0, (c) Landesbetrieb Geoinformation und
Vermessung (LGV) Hamburg. Aus dem 1,3-GB-ZIP werden per HTTP-Range nur die
1-km-Kacheln des Ausschnitts geladen.

Die Rasterlogik (``spill_elevation``, ``flood_timing``) ist netzfrei und
braucht nur numpy + scikit-image. Fuer Download/GeoTIFF: ``uv sync --extra
gelaende`` (rasterio, remotezip, scikit-image).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DGM1_URL, OVER_PNP_NHN_M


def cm_pnp_to_m_nhn(w_cm: pd.Series, gauge_zero_m_nhn: float = OVER_PNP_NHN_M):
    """Wasserstand cm ueber PNP -> m ueber NHN (Bezug des DGM1)."""
    return w_cm / 100.0 + gauge_zero_m_nhn


# --- Gelaende laden ----------------------------------------------------------


DGM1_TILE = "dgm1_32_{e}_{n}_1_hh_2022.tif"


def tile_names(
    bbox: tuple[float, float, float, float], pattern: str = DGM1_TILE
) -> list[str]:
    """Dateinamen der 1-km-Kacheln, die ``bbox`` (xmin, ymin, xmax, ymax in
    EPSG:25832) schneiden. ``pattern`` mit ``{e}``/``{n}`` = linke untere Ecke
    in km (LGV-Schema fuer DGM1 und LoD2)."""
    xmin, ymin, xmax, ymax = bbox
    return [
        pattern.format(e=e, n=n)
        for e in range(int(xmin // 1000), int(np.ceil(xmax / 1000)))
        for n in range(int(ymin // 1000), int(np.ceil(ymax / 1000)))
    ]


def fetch_tiles(
    bbox: tuple[float, float, float, float],
    out_dir: str | Path,
    url: str = DGM1_URL,
    pattern: str = DGM1_TILE,
) -> list[Path]:
    """Laedt die Kacheln fuer ``bbox`` aus dem Hamburg-ZIP (nur diese Bytes) nach
    ``out_dir``. Bereits vorhandene Kacheln werden nicht erneut geladen.
    Kacheln ausserhalb Hamburgs (z. B. Niedersachsen-Ufer) fehlen im ZIP."""
    from remotezip import RemoteZip

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    want = set(tile_names(bbox, pattern))
    have = {p.name: p for p in out.iterdir() if p.name in want}
    if missing := want - have.keys():
        with RemoteZip(url) as z:
            for info in z.infolist():
                name = info.filename.rsplit("/", 1)[-1]
                if name in missing:
                    (out / name).write_bytes(z.read(info))
                    have[name] = out / name
    return sorted(have.values())


@dataclass
class Terrain:
    """Gelaendehoehe ``z`` (m NHN, NaN = keine Daten, meist Wasserflaeche der
    Elbe) auf einem Nord-oben-Raster. ``transform`` ist die affine Abbildung
    (rasterio/GDAL-Konvention) Zeile/Spalte -> EPSG:25832."""

    z: np.ndarray
    transform: object
    crs: str = "EPSG:25832"

    @property
    def extent(self) -> tuple[float, float, float, float]:
        """(left, right, bottom, top) fuer matplotlib ``imshow``."""
        t = self.transform
        h, w = self.z.shape
        return (t.c, t.c + w * t.a, t.f + h * t.e, t.f)


def load_terrain(paths: list[Path], bbox: tuple[float, float, float, float]) -> Terrain:
    """Mosaik der Kacheln, auf ``bbox`` zugeschnitten. Fehlwerte (-9999 und
    die GeoTIFF-Nodata) werden NaN; Bereiche ohne Kachel ebenso."""
    import rasterio
    from rasterio.merge import merge

    srcs = [rasterio.open(p) for p in paths]
    try:
        mosaic, transform = merge(srcs, bounds=bbox, nodata=np.nan, dtype="float32")
    finally:
        for s in srcs:
            s.close()
    z = mosaic[0]
    z[z < -100] = np.nan  # -9999 ausserhalb Hamburgs
    z[water_fill_mask(z)] = np.nan
    return Terrain(z=z, transform=transform)


# --- Rasterlogik (netzfrei) --------------------------------------------------


def water_fill_mask(z: np.ndarray, min_cells: int = 10_000) -> np.ndarray:
    """Wasserflaechen im DGM1: Das LGV fuellt sie mit glatten Platzhaltern (Elbe
    bei Overwerder exakt 2,00 m, Hohendeicher See 1,00 m). Ungefiltert wirkt die
    Elbe-Flaeche als kuenstliche 2-m-Schwelle. Erkannt als grosse,
    zusammenhaengende Flaechen mit ganzzahligem Wert."""
    from scipy import ndimage

    labels, n = ndimage.label(z == np.round(z))
    if n == 0:
        return np.zeros(z.shape, dtype=bool)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return sizes[labels] >= min_cells


def river_mask(z: np.ndarray) -> np.ndarray:
    """Groesste zusammenhaengende Fehlwert-Flaeche = Strom (die Elbe ist im DGM1
    ausgespart). Kleine Fehlwert-Inseln im Binnenland zaehlen nicht."""
    from scipy import ndimage

    labels, n = ndimage.label(np.isnan(z))
    if n == 0:
        raise ValueError("kein Fehlwert-Bereich -> river-Maske explizit uebergeben")
    sizes = ndimage.sum_labels(np.ones_like(z), labels, index=np.arange(1, n + 1))
    return labels == 1 + int(np.argmax(sizes))


def spill_elevation(z: np.ndarray, river: np.ndarray) -> np.ndarray:
    """Ueberlaufhoehe je Zelle (m NHN): niedrigster Wasserstand im Strom, bei dem
    die Zelle ueber einen zusammenhaengenden Weg nass wird (8er-Nachbarschaft).

    Minimax-Pfad per morphologischer Rekonstruktion durch Erosion: Start = ``z``
    im Strom, sonst +inf; Maske = ``z``. NaN ausserhalb des Stroms gilt als
    undurchlaessig (bleibt NaN).
    """
    from skimage.morphology import reconstruction

    land = np.isfinite(z) & ~river
    floor = np.nanmin(z[land]) - 1.0
    top = np.nanmax(z[land]) + 1.0
    mask = np.where(land, z, np.where(river, floor, top))
    seed = np.where(river, floor, top)
    spill = reconstruction(seed, mask, method="erosion", footprint=np.ones((3, 3)))
    spill[~land] = np.nan
    return spill


def travel_distance(
    spill: np.ndarray, river: np.ndarray, cell_m: float = 1.0, step_m: float = 0.1
) -> np.ndarray:
    """Fliessweg (m) vom Strom bis zu jeder Zelle, nur ueber Zellen, die zu dem
    Zeitpunkt schon nass sind: Eine Zelle mit Ueberlaufhoehe ``s`` wird ueber
    Zellen mit Ueberlaufhoehe <= ``s`` erreicht (auf ``step_m`` gerundet). Der
    Weg im Strom selbst zaehlt (fast) nicht. NaN = nie erreichbar.

    Teilt man den Weg durch eine Fliessgeschwindigkeit, ergibt sich die
    Verzoegerung gegenueber dem Badewannen-Modell (Wasser sofort ueberall).
    """
    from skimage.graph import MCP_Geometric

    dist = np.full(spill.shape, np.nan)
    land = np.isfinite(spill)
    if not land.any() or not river.any():
        return dist
    k = np.full(spill.shape, -1, dtype=int)
    k[land] = np.ceil(np.round(spill[land] / step_m, 6)).astype(int)
    starts = np.argwhere(river)
    for kk in np.unique(k[land]):
        h = kk * step_m + 1e-9
        cost = np.where(river, 1e-3, np.where(land & (spill <= h), 1.0, np.inf))
        cum, _ = MCP_Geometric(cost).find_costs(starts)
        sel = k == kk
        dist[sel] = cum[sel] * cell_m
    dist[~np.isfinite(dist)] = np.nan
    return dist


def flood_timing(
    spill: np.ndarray,
    z: np.ndarray,
    level_m_nhn: pd.Series,
    drain_m_per_h: float = 0.0,
    pond_min_m: float = 0.01,
) -> dict[str, np.ndarray]:
    """Zeitpunkte und Kennwerte je Zelle fuer eine Wasserstandskurve (m NHN).

    Ablauf: Faellt der Strom unter die Ueberlaufhoehe, laeuft eine Zelle nur bis
    auf diese Schwelle leer. In Senken hinter einem Sommerdeich bleibt Wasser
    bis zur Deichkrone stehen (Tiefe ``spill - z``) und sinkt danach mit
    ``drain_m_per_h`` (Siele/Versickerung; 0 = bleibt bis Reihenende stehen).

    Rueckgabe (alle wie ``z``, NaN/NaT = bleibt trocken):

    * ``onset``: erster Zeitpunkt nass (datetime64[ns], UTC)
    * ``inflow_end``: Ende des letzten Zeitschritts mit Verbindung zum Strom
    * ``end``: Zelle wieder trocken (bei stehendem Wasser ggf. erst danach)
    * ``hours_wet``: nasse Zeit in Stunden (Verbindung zum Strom + Stauwasser)
    * ``max_depth``: maximale Wassertiefe in m (Scheitel - Gelaende)
    * ``residual_depth``: Stauwasser-Tiefe am Reihenende in m (0 = abgelaufen)
    """
    level = level_m_nhn.sort_index().dropna()
    t = level.index.tz_convert("UTC").tz_localize(None).values
    h = level.to_numpy(dtype=float)
    dt_h = np.diff(t).astype("timedelta64[s]").astype(float) / 3600.0
    dt_h = np.append(dt_h, np.median(dt_h) if len(dt_h) else 0.0)
    step = (dt_h * 3600e9).astype("timedelta64[ns]")

    wet = np.isfinite(spill) & (spill <= h.max())
    s = np.where(wet, spill, np.inf)
    i_on = np.minimum(
        np.searchsorted(np.maximum.accumulate(h), s, side="left"), len(h) - 1
    )
    i_off = np.clip(
        len(h) - 1 - np.searchsorted(np.maximum.accumulate(h[::-1]), s, side="left"),
        0,
        len(h) - 1,
    )
    # Dauer mit Verbindung: Zeitschritte mit h >= spill, gewichtet mit Laenge
    order = np.argsort(h)
    cum = np.concatenate([[0.0], np.cumsum(dt_h[order][::-1])])
    connected_h = cum[len(h) - np.searchsorted(h[order], s, side="left")]

    # Stauwasser nach dem letzten Kontakt bis Reihenende (bzw. bis abgelaufen)
    inflow_end = t[i_off] + step[i_off]
    left_h = (t[-1] + step[-1] - inflow_end) / np.timedelta64(1, "h")
    pond = np.where(wet & (spill - z >= pond_min_m), spill - z, 0.0)
    pond_h = left_h if drain_m_per_h <= 0 else np.minimum(pond / drain_m_per_h, left_h)
    pond_h = np.where(pond > 0, pond_h, 0.0)
    residual = pond if drain_m_per_h <= 0 else pond - drain_m_per_h * pond_h
    pond_end = inflow_end + (pond_h * 3600e9).astype("timedelta64[ns]")

    nat = np.datetime64("NaT", "ns")
    return {
        "onset": np.where(wet, t[i_on], nat),
        "inflow_end": np.where(wet, inflow_end, nat),
        "end": np.where(wet, np.where(pond > 0, pond_end, t[i_off]), nat),
        "hours_wet": np.where(wet, connected_h + pond_h, np.nan),
        "max_depth": np.where(wet, h.max() - z, np.nan),
        "residual_depth": np.where(wet, np.maximum(residual, 0.0), np.nan),
    }


def depth_at(
    spill: np.ndarray,
    z: np.ndarray,
    level_m_nhn: pd.Series,
    when: pd.Timestamp,
    drain_m_per_h: float = 0.0,
    pond_min_m: float = 0.01,
) -> np.ndarray:
    """Wassertiefe (m, NaN = trocken) zum Zeitpunkt ``when``: verbundene Zellen
    stehen auf Stromniveau, Senken behalten ihr Stauwasser (sinkend mit
    ``drain_m_per_h``)."""
    past = level_m_nhn.sort_index().dropna()[:when]
    tm = flood_timing(spill, z, past, drain_m_per_h, pond_min_m)
    now = past.index[-1].tz_convert("UTC").tz_localize(None).to_datetime64()
    hrs = np.maximum((now - tm["inflow_end"]) / np.timedelta64(1, "h"), 0.0)
    surface = np.maximum(past.iloc[-1], spill - drain_m_per_h * hrs)
    depth = np.where(np.isnat(tm["onset"]), np.nan, surface - z)
    return np.where(depth >= pond_min_m, depth, np.nan)


def height_timing_table(
    z: np.ndarray, timing: dict[str, np.ndarray], area: np.ndarray, step_m=0.1
) -> pd.DataFrame:
    """Wie die Gelaendehoehe den Zeitpunkt steuert: Zellen in ``area`` nach
    Hoehe in ``step_m``-Klassen; je Klasse Flaeche (m^2 bei 1-m-Raster), Anteil
    nass, mittlerer Beginn, Dauer und Tiefe."""
    sel = area & np.isfinite(z)
    df = pd.DataFrame(
        {
            "z": z[sel],
            "onset": pd.to_datetime(timing["onset"][sel]).tz_localize("UTC"),
            "hours_wet": timing["hours_wet"][sel],
            "max_depth": timing["max_depth"][sel],
        }
    )
    df["z_class"] = (np.floor(df["z"] / step_m) * step_m).round(2)
    g = df.groupby("z_class")
    return pd.DataFrame(
        {
            "cells": g.size(),
            "wet_share": g["onset"].apply(lambda s: s.notna().mean()),
            "onset_median": g["onset"].median(),
            "hours_wet_median": g["hours_wet"].median(),
            "max_depth_median": g["max_depth"].median(),
        }
    )


def write_geotiff(path: str | Path, terrain: Terrain, data: np.ndarray) -> None:
    """Float-Raster mit Georeferenz von ``terrain`` als komprimiertes GeoTIFF."""
    import rasterio

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs=terrain.crs,
        transform=terrain.transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(data.astype("float32"), 1)
