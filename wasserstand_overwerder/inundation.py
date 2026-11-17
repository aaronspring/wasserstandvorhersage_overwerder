"""Gelaende fuer die Overhaken-Karte der Web-App: DGM1 (LGV Hamburg) laden,
Ueberlaufhoehe und Fliessweg je Rasterzelle.

Badewannen-Modell mit hydraulischer Konnektivitaet: Eine Zelle wird nass,
sobald der Elbe-Wasserstand ihre **Ueberlaufhoehe** erreicht. Das ist die
niedrigste Hoehe, ueber die Wasser vom Strom aus zur Zelle gelangen kann
(Minimax-Pfad: die hoechste Schwelle auf dem guenstigsten Weg). Eine Senke
hinter einem Sommerdeich wird also erst nass, wenn der Deich ueberstroemt wird,
und das Hinterland hinter dem Hauptdeich bleibt trocken. Die Ueberlaufhoehe
haengt nur vom Gelaende ab (morphologische Rekonstruktion durch Erosion); die
Zeitpunkte rechnet die Web-App daraus fuer jeden Wasserstand selbst.

Gelaende: DGM1 2022 (1-m-Raster, ETRS89/UTM32 = EPSG:25832, Hoehen m ueber
NHN/DHHN2016, +/- 15 cm) aus dem Transparenzportal Hamburg; Datenlizenz
Deutschland - Namensnennung 2.0, (c) Landesbetrieb Geoinformation und
Vermessung (LGV) Hamburg. Aus dem 1,3-GB-ZIP werden per HTTP-Range nur die
1-km-Kacheln des Ausschnitts geladen. Braucht ``uv sync --extra gelaende``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import DGM1_URL, DGMW_URL

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
    Kacheln ausserhalb Hamburgs (z. B. Niedersachsen-Ufer) fehlen im ZIP; sie
    werden in ``out_dir/absent.txt`` vermerkt, damit ein voller Cache ohne Netz
    auskommt (Datei loeschen, um neu zu pruefen)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    absent_file = out / "absent.txt"
    absent = set(absent_file.read_text().split()) if absent_file.exists() else set()
    want = set(tile_names(bbox, pattern))
    have = {p.name: p for p in out.iterdir() if p.name in want}
    if missing := want - have.keys() - absent:
        from remotezip import RemoteZip

        with RemoteZip(url) as z:
            for info in z.infolist():
                name = info.filename.rsplit("/", 1)[-1]
                if name in missing:
                    (out / name).write_bytes(z.read(info))
                    have[name] = out / name
        absent |= missing - have.keys()
        absent_file.write_text("\n".join(sorted(absent)) + "\n")
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


def load_riverbed(
    terrain: Terrain, cache_dir: str | Path, url: str = DGMW_URL
) -> np.ndarray:
    """Flussbett-Hoehen (m NHN, NaN = keine Daten) aus dem DGM-W auf dem Raster
    von ``terrain``. Liest per GDAL ``/vsicurl/`` (HTTP-Range) nur den
    Ausschnitt; Cache ``cache_dir/dgmw_<xmin>_<ymax>_<w>x<h>.npy``."""
    t = terrain.transform
    h, w = terrain.z.shape
    cache = Path(cache_dir) / f"dgmw_{t.c:.0f}_{t.f:.0f}_{w}x{h}.npy"
    if cache.exists():
        return np.load(cache)
    import rasterio
    from rasterio.windows import from_bounds

    xmin, xmax, ymin, ymax = terrain.extent
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}
    with rasterio.Env(**env), rasterio.open(f"/vsicurl/{url}") as src:
        if abs(src.transform.a - t.a) > 1e-9 or abs(src.transform.e - t.e) > 1e-9:
            raise ValueError("DGM-W-Raster passt nicht zur Zellgroesse des DGM1")
        win = from_bounds(xmin, ymin, xmax, ymax, src.transform).round_offsets()
        bed = src.read(1, window=win, boundless=True, fill_value=np.nan)
    bed = bed.astype("float32")[:h, :w]
    bed[~(bed > -100)] = np.nan
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, bed)
    return bed


# --- Rasterlogik (netzfrei) --------------------------------------------------


def fill_riverbed(z: np.ndarray, river: np.ndarray, bed: np.ndarray) -> np.ndarray:
    """``z`` mit dem Flussbett aufgefuellt, nur im Strom (``river``, die
    DGM1-Luecke). Seen und andere Fehlwert-Inseln bleiben NaN."""
    out = z.copy()
    fill = river & np.isfinite(bed)
    out[fill] = bed[fill]
    return out


def channel_mask(z: np.ndarray, river: np.ndarray, max_m: float) -> np.ndarray:
    """Strom als Wasserquelle: groesste zusammenhaengende Flaeche des Flussbetts
    (``river``) unter ``max_m`` m NHN. Dort steht bei jeder Tide Wasser."""
    from scipy import ndimage

    deep = river & (z <= max_m)
    labels, n = ndimage.label(deep, structure=np.ones((3, 3)))
    if n == 0:
        raise ValueError(f"kein Flussbett unter {max_m} m NHN im Strom")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(np.argmax(sizes))


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
