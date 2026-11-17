"""Web-Asset der Overhaken-Karte: Ausschnitt, Kodierung, Gebaeude (netzfrei)."""

import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import inundation, inundation_web
from wasserstand_overwerder.inundation import Terrain


def make_terrain():
    z = np.full((20, 40), 2.5)
    z[:, :10] = np.nan  # Strom
    z[:, 20] = 3.0
    z[:, 21:30] = 2.0
    z[:, 30:] = 8.0
    z[5, 35] = np.nan  # kleines sonstiges Wasser
    # Nordwest-Ecke bei (1000, 2020), 1-m-Zellen
    return Terrain(z=z, transform=SimpleNamespace(a=1.0, c=1000.0, e=-1.0, f=2020.0))


def test_build_asset_roundtrip():
    ter = make_terrain()
    river = inundation.river_mask(ter.z)
    spill = inundation.spill_elevation(ter.z, river)
    bldg = pd.DataFrame(
        {
            "nr": [1],
            "alkis_id": ["X"],
            "address": [""],
            "base_m": [2.0],
            "spill_m": [3.0],
            "footprint": [np.array([[1022.0, 2010.0], [1024.0, 2010.0], [1024, 2012]])],
        }
    )
    a = inundation_web.build_asset(
        ter,
        river,
        spill,
        (1000, 2000, 1040, 2020),
        step=2,
        gauge_zero_m_nhn=-5.098,
        bldg=bldg,
    )
    assert (a["width"], a["height"]) == (20, 10)
    assert a["extent"] == [1000.0, 2000.0, 1040.0, 2020.0]
    z = inundation_web.decode(a, "z_cm")
    sp = inundation_web.decode(a, "spill_cm")
    cls = inundation_web.decode(a, "cls")
    assert (cls[:, :5] == inundation_web.RIVER).all()
    assert (z[:, :5] == inundation_web.NODATA).all()
    assert z[0, 6] == 250 and sp[0, 11] == 300  # Senke erst ab Deichkrone
    assert inundation_web.decode(a, "shade").shape == (10, 20)
    assert a["buildings"][0]["ring"][0] == [22.0, 10.0]
    assert a["buildings"][0]["spill_m"] == 3.0


def test_dop_url_matches_view():
    url = inundation_web.dop_url((0, 0, 540, 420), 2024)
    assert "BBOX=0%2C0%2C540%2C420" in url
    assert "WIDTH=1080" in url and "HEIGHT=840" in url and "TIME=2024" in url


def test_lag_aligned_when_margin_clipped_at_edge():
    # Ausschnitt beginnt bei Zeile/Spalte 1 (ungerade) direkt am Modellrand:
    # das grobe Raster fuer den Fliessweg muss phasengleich zu z bleiben.
    # Ein Deich (8 m) hat nur in Zeile 5 eine Luecke; die Senke dahinter ist
    # nur ueber diese Luecke erreichbar -> im falschen Raster (gerade Zeilen)
    # waere sie unerreichbar und haette Fliesszeit 0.
    z = np.full((20, 40), 2.5)
    z[:, :10] = np.nan
    z[:, 21] = 8.0  # ungerade Spalte -> im 2-m-Raster des Ausschnitts enthalten
    z[5, 21] = 2.5
    z[:, 22:] = 2.0
    ter = Terrain(z=z, transform=SimpleNamespace(a=1.0, c=1000.0, e=-1.0, f=2020.0))
    river = inundation.river_mask(z)
    spill = inundation.spill_elevation(z, river)
    a = inundation_web.build_asset(
        ter,
        river,
        spill,
        (1001, 2000, 1039, 2019),
        step=2,
        gauge_zero_m_nhn=-5.098,
        flow_m_s=1 / 60,  # 1 min je m
    )
    lag = inundation_web.decode(a, "lag_min")
    # Senke: Vollraster-Spalte 1 + 2 j >= 23 -> j >= 11; Zeile 5 -> i = 2
    assert (lag[:, 11:] > 10).all()
    assert lag[2, 11] < lag[8, 11]  # an der Luecke kuerzer als weit weg
