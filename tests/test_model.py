"""Synthetik-Test: Kalibrierung findet bekannte Parameter einer M2-Tide wieder.

Ausfuehren mit `python tests/test_model.py` oder `pytest tests/`.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder.model import Params, calibrate, interpolate, recent_bias_cm

M2_MIN = 12.42 * 60.0  # M2-Periode in Minuten


def synthetic_tide(t0: pd.Timestamp, days: float, lag_minutes: float,
                   mean_cm: float, amp_cm: float, freq: str = "5min") -> pd.Series:
    """Asymmetrische Tidekurve (M2 + Obertiden M4/M6), um `lag` verschoben.

    Die Obertiden sind wichtig: bei einer reinen Sinuskurve waere die
    Laufzeit in der Kalibrierung nicht identifizierbar.
    """
    idx = pd.date_range(t0, t0 + pd.Timedelta(days=days), freq=freq, tz="UTC")
    minutes = (idx - t0).total_seconds() / 60.0
    phase = 2.0 * np.pi * (minutes - lag_minutes) / M2_MIN
    spring_neap = 1.0 + 0.15 * np.sin(2.0 * np.pi * minutes / (14.77 * 24 * 60))
    shape = (np.cos(phase) + 0.25 * np.cos(2.0 * phase - 1.0)
             + 0.10 * np.cos(3.0 * phase + 0.5))
    return pd.Series(mean_cm + amp_cm * spring_neap * shape, index=idx)


def build_scenario():
    """St. Pauli fuehrt, Overwerder +45 min, Zollenspieker +70 min."""
    t0 = pd.Timestamp("2026-06-01", tz="UTC")
    p = Params()  # Elbe-km-Defaults: f ~ 0.282
    tau_true = 70.0
    f = p.frac
    down = synthetic_tide(t0, 12, 0.0, 510, 180)                    # St. Pauli
    target = synthetic_tide(t0, 12, tau_true * (1 - f), 505, 165)   # Overwerder
    up = synthetic_tide(t0, 12, tau_true, 500, 150)                 # Zollenspieker
    return up, down, target, tau_true


def test_calibrate_recovers_lag():
    up, down, target, tau_true = build_scenario()
    params, metrics = calibrate(up, down, target)
    assert abs(params.tau_minutes - tau_true) <= 5.0, params.tau_minutes
    assert metrics["rmse_cm"] < 5.0, metrics
    assert metrics["corr"] > 0.999, metrics
    assert 0.0 < params.a_down < params.a_up  # Zollenspieker liegt naeher


def test_interpolate_matches_target():
    up, down, target, _ = build_scenario()
    params, _ = calibrate(up, down, target)
    est = interpolate(up, down, params)
    both = pd.concat({"est": est, "obs": target}, axis=1, join="inner").dropna()
    rmse = float(np.sqrt(((both["est"] - both["obs"]) ** 2).mean()))
    assert rmse < 5.0, rmse
    assert abs(recent_bias_cm(est, target)) < 3.0


def test_default_params_reasonable():
    p = Params()
    assert 0.25 < p.frac < 0.32
    w_up, w_down = p.weights()
    assert abs(w_up + w_down - 1.0) < 1e-9
    assert w_up > w_down  # Zollenspieker ist der naehere Pegel


def test_params_roundtrip(tmp_path=None):
    import tempfile
    p = Params(tau_minutes=72.0, a_up=0.7, a_down=0.3, offset_cm=-2.5)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "params.json")
        p.save(path)
        q = Params.load(path)
    assert q == p


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("Alle Tests bestanden.")
