"""Netzfreie Tests fuer die Parzellen-Zuordnung der Overhaken-Gebaeude."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace

import numpy as np

from wasserstand_overwerder import buildings, config


def test_label_parzellen_keeps_only_mapped_and_labels():
    df = pd.DataFrame(
        {"nr": [1, 2, 3], "alkis_id": ["A", "B", "C"], "x": [0.0, 1.0, 2.0]}
    )
    out = buildings.label_parzellen(df, {"A": "101", "C": "Garage"})
    assert list(out["alkis_id"]) == ["A", "C"]
    assert list(out["parzelle"]) == ["101", "Garage"]
    assert list(out["nr"]) == [1, 3]


def test_config_parzellen_plausible():
    p = config.OVERHAKEN_PARZELLEN
    nums = [int(v) for v in p.values() if v.isdigit()]
    assert all(100 <= n <= 141 for n in nums)
    manual = set(config.OVERHAKEN_MANUELLE_GEBAEUDE)
    assert all(k.startswith("DEHHALK") or k in manual for k in p)


def test_manual_buildings_base_from_terrain():
    # 10x10 Raster, 1 m, Ursprung (100, 110) oben links; Hoehe = Zeilenindex.
    z = np.repeat(np.arange(10, dtype=float)[:, None], 10, axis=1)
    terrain = SimpleNamespace(
        z=z, transform=SimpleNamespace(a=1.0, c=100.0, e=-1.0, f=110.0)
    )
    fp = {"manuell-1": ((102.0, 107.0), (105.0, 107.0), (105.0, 104.0), (102.0, 104.0))}
    df = buildings.manual_buildings(fp, terrain)
    row = df.iloc[0]
    assert row["alkis_id"] == "manuell-1"
    assert np.allclose(row["footprint"][0], row["footprint"][-1])  # Ring geschlossen
    # y 104..107 -> Zeilen 3..5 (Zellmitten), tiefste Hoehe = 3
    assert row["base_m"] == 3.0
    assert (row["x"], row["y"]) == (103.5, 105.5)


def test_manual_buildings_closes_ring_at_utm_scale():
    # Grosse UTM-Koordinaten: relative Toleranzen (np.allclose) wuerden die
    # offenen Ecken als "gleich" werten.
    terrain = SimpleNamespace(
        z=np.zeros((400, 400)),
        transform=SimpleNamespace(a=1.0, c=573200.0, e=-1.0, f=5921500.0),
    )
    df = buildings.manual_buildings(config.OVERHAKEN_MANUELLE_GEBAEUDE, terrain)
    for fp in df["footprint"]:
        assert np.array_equal(fp[0], fp[-1]) and len(fp) >= 5


def test_manual_buildings_are_labelled():
    for key in config.OVERHAKEN_MANUELLE_GEBAEUDE:
        assert key in config.OVERHAKEN_PARZELLEN
