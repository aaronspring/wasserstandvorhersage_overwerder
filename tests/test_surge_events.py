"""Netzfreie Tests fuer die Ereignis-Kurven der Overhaken-Karte."""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import config, surge_events


def _minutely(peak: pd.Timestamp, peak_cm: float = 1100.0) -> pd.Series:
    idx = pd.date_range(
        peak - pd.Timedelta(days=4), peak + pd.Timedelta(days=1), freq="min"
    )
    h = (idx - peak).total_seconds() / 3600
    tide = 150 * np.cos(2 * np.pi * h / 12.42)
    surge = (peak_cm - 650 - 150) * np.exp(-0.5 * (h / 8) ** 2)
    return pd.Series(650 + tide + surge, index=idx)


def test_peak_utc_respects_dst():
    assert surge_events.peak_utc("2013-12-06 06:31") == pd.Timestamp(
        "2013-12-06 05:31", tz="UTC"
    )
    assert surge_events.peak_utc("2023-07-01 12:00") == pd.Timestamp(
        "2023-07-01 10:00", tz="UTC"
    )


def test_event_series_window_and_exact_peak():
    peak = pd.Timestamp("2013-12-06 05:31", tz="UTC")
    s = _minutely(peak)
    out, t_max, v_max = surge_events.event_series(s, peak + pd.Timedelta(minutes=20))
    assert t_max == peak and abs(v_max - 1100.0) < 1e-6
    assert out.max() == v_max and out.idxmax() == peak
    assert out.index[0] >= peak + pd.Timedelta(minutes=20) - pd.Timedelta(hours=72)
    assert out.index[-1] <= peak + pd.Timedelta(minutes=20) + pd.Timedelta(hours=6)
    assert out.index.is_monotonic_increasing and out.index.is_unique


def test_build_events_uses_config():
    parts = [
        _minutely(surge_events.peak_utc(t))
        for t in config.STURMFLUT_SCHEITEL_ZEIT.values()
    ]
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated()]
    ev = surge_events.build_events(s)
    assert [e["rank"] for e in ev] == sorted(config.STURMFLUT_SCHEITEL_CM)
    for e in ev:
        assert e["series"][0][0] < e["peak"] < e["series"][-1][0]
        assert max(v for _, v in e["series"]) == e["peak_cm"]
