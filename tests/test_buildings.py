"""Netzfreie Tests fuer die Parzellen-Zuordnung der Overhaken-Gebaeude."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
    assert all(k.startswith("DEHHALK") for k in p)
