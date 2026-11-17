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
