"""Synthetik-Tests fuer die Sturmflut-Erkennung/-Klassifikation (netzfrei).

Baut eine minuetliche M2-Tide mit bekanntem MThw, injiziert eine Sturmflut und
prueft, dass Thw-Erkennung, MThw-Schaetzung und BSH-Klassifikation stimmen.
Ausfuehren mit `pytest tests/` oder `python tests/test_sturmflut.py`.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import sturmflut

M2_MIN = 12.42 * 60.0  # M2-Periode in Minuten


def synthetic_series(days: float, mean_cm: float, amp_cm: float) -> pd.Series:
    """Minuetliche M2-Tide (mean +/- amp) mit leichter Obertide, tz-aware UTC."""
    t0 = pd.Timestamp("2001-01-01", tz="UTC")
    idx = pd.date_range(t0, t0 + pd.Timedelta(days=days), freq="1min", tz="UTC")
    minutes = (idx - t0).total_seconds() / 60.0
    phase = 2.0 * np.pi * minutes / M2_MIN
    shape = np.cos(phase) + 0.20 * np.cos(2.0 * phase - 1.0)
    return pd.Series(mean_cm + amp_cm * shape, index=idx)


def test_tidal_highs_spacing_and_mthw():
    """Thw liegen im Halbtags-Takt; MThw ~ mean + amp (Scheitel der M2)."""
    mean_cm, amp_cm = 500.0, 200.0
    s = synthetic_series(days=20, mean_cm=mean_cm, amp_cm=amp_cm)
    highs = sturmflut.tidal_highs(s, min_height_cm=300.0)
    # ~2 Thw pro Tag ueber 20 Tage
    assert 36 <= len(highs) <= 42
    dt_min = np.diff(highs.index.values).astype("timedelta64[m]").astype(float)
    assert abs(np.median(dt_min) - M2_MIN) < 15.0  # ~745 min Abstand
    mthw = sturmflut.mean_high_water(highs)
    # Scheitel der reinen M2 liegt nahe mean+amp; Obertide verschiebt leicht.
    assert abs(mthw - (mean_cm + amp_cm)) < 40.0


def test_classify_thresholds():
    """BSH-Grenzen: <150 kein, 150/250/350 -> die drei Klassen."""
    assert sturmflut.classify(149.9) is None
    assert sturmflut.classify(150.0) == "Sturmflut"
    assert sturmflut.classify(200.0) == "Sturmflut"
    assert sturmflut.classify(250.0) == "schwere Sturmflut"
    assert sturmflut.classify(349.9) == "schwere Sturmflut"
    assert sturmflut.classify(400.0) == "sehr schwere Sturmflut"


def test_injected_surge_is_detected_and_classified():
    """Eine ueber MThw+2,6 m injizierte Flut wird als 'schwere' erkannt."""
    mean_cm, amp_cm = 500.0, 200.0
    s = synthetic_series(days=30, mean_cm=mean_cm, amp_cm=amp_cm).copy()
    highs0 = sturmflut.tidal_highs(s, min_height_cm=300.0)
    mthw = sturmflut.mean_high_water(highs0)
    # Sturmflut-Scheitel: MThw + 260 cm um einen Thw-Zeitpunkt herum aufsetzen.
    peak_t = highs0.index[10]
    win = (s.index >= peak_t - pd.Timedelta("60min")) & (
        s.index <= peak_t + pd.Timedelta("60min")
    )
    bump = mthw + 260.0 - float(s[win].max())
    s.loc[win] = s.loc[win] + bump

    highs = sturmflut.tidal_highs(s, min_height_cm=300.0)
    surges = sturmflut.surge_tides(highs, mthw)
    assert len(surges) == 1
    row = surges.iloc[0]
    assert row["klasse"] == "schwere Sturmflut"
    assert 250.0 <= row["above_mthw"] < 350.0
    assert row["month"] == surges.index[0].tz_convert("Europe/Berlin").month


def test_linear_trend_recovers_slope():
    """linear_trend findet eine bekannte Steigung und meldet Signifikanz."""
    x = np.arange(2000, 2025, dtype=float)
    y = 2.0 * (x - 2000) + 5.0  # exakt linear
    tr = sturmflut.linear_trend(x, y)
    assert abs(tr["slope"] - 2.0) < 1e-9
    assert tr["r"] > 0.999
    assert tr["p"] < 0.01


if __name__ == "__main__":
    test_tidal_highs_spacing_and_mthw()
    test_classify_thresholds()
    test_injected_surge_is_detected_and_classified()
    test_linear_trend_recovers_slope()
    print("ok")
