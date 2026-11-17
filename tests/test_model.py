"""Synthetik-Test: Kalibrierung findet bekannte Parameter einer M2-Tide wieder.

Ausfuehren mit `python tests/test_model.py` oder `pytest tests/`.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder.model import (
    Params,
    calibrate,
    interpolate,
    is_plausible,
    load_params,
    recent_bias_cm,
)

M2_MIN = 12.42 * 60.0  # M2-Periode in Minuten


def synthetic_tide(
    t0: pd.Timestamp,
    days: float,
    lag_minutes: float,
    mean_cm: float,
    amp_cm: float,
    freq: str = "5min",
) -> pd.Series:
    """Asymmetrische Tidekurve (M2 + Obertiden M4/M6), um `lag` verschoben.

    Die Obertiden sind wichtig: bei einer reinen Sinuskurve waere die
    Laufzeit in der Kalibrierung nicht identifizierbar.
    """
    idx = pd.date_range(t0, t0 + pd.Timedelta(days=days), freq=freq, tz="UTC")
    minutes = (idx - t0).total_seconds() / 60.0
    phase = 2.0 * np.pi * (minutes - lag_minutes) / M2_MIN
    spring_neap = 1.0 + 0.15 * np.sin(2.0 * np.pi * minutes / (14.77 * 24 * 60))
    shape = (
        np.cos(phase)
        + 0.25 * np.cos(2.0 * phase - 1.0)
        + 0.10 * np.cos(3.0 * phase + 0.5)
    )
    return pd.Series(mean_cm + amp_cm * spring_neap * shape, index=idx)


def build_scenario():
    """St. Pauli fuehrt, Overwerder +45 min, Zollenspieker +70 min."""
    t0 = pd.Timestamp("2026-06-01", tz="UTC")
    p = Params()  # Elbe-km-Defaults: f ~ 0.282
    tau_true = 70.0
    f = p.frac
    down = synthetic_tide(t0, 12, 0.0, 510, 180)  # St. Pauli
    target = synthetic_tide(t0, 12, tau_true * (1 - f), 505, 165)  # Overwerder
    up = synthetic_tide(t0, 12, tau_true, 500, 150)  # Zollenspieker
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


def test_calibrate_marks_free_fit():
    """Der gesunde Fall bleibt der freie Fit (nicht eingeschraenkt)."""
    up, down, target, _ = build_scenario()
    _, metrics = calibrate(up, down, target)
    assert metrics["restricted"] is False, metrics


def test_is_plausible_rejects_degenerate():
    assert is_plausible(Params(tau_minutes=60.0, a_up=0.6, a_down=0.4, offset_cm=5.0))
    # Kollaps auf einen Pegel plus grosse Konstante (so gesehen vor Xaver 2013)
    assert not is_plausible(
        Params(tau_minutes=170.0, a_up=1.08, a_down=0.03, offset_cm=-85.0)
    )
    assert not is_plausible(Params(a_up=-0.2, a_down=1.2, offset_cm=0.0))  # negativ
    assert not is_plausible(Params(a_up=0.7, a_down=0.3, offset_cm=-80.0))  # Offset


def test_calibrate_falls_back_when_only_degenerate_fits():
    """Laesst sich das Ziel nur mit riesigem Offset treffen, ist jeder freie Fit
    entartet -> eingeschraenkte Kalibrierung mit festen Entfernungsgewichten."""
    up, down, _, _ = build_scenario()
    target = up - 200.0  # kein Gewichtspaar in [0,1] kommt ohne grossen c aus
    params, metrics = calibrate(up, down, target)
    assert metrics["restricted"] is True, metrics
    assert metrics["rejected"] > 0, metrics
    assert params.weights() == Params().weights()  # Gewichte kamen nicht aus den Daten


def test_calibrate_keeps_weights_plausible():
    """Egal wie die Daten aussehen: die Gewichte bleiben eine Konvexkombination."""
    up, down, target, _ = build_scenario()
    for obs in (target, up - 90.0, down + 40.0):
        params, _ = calibrate(up, down, obs)
        a_up, a_down = params.weights()
        assert 0.0 <= a_up <= 1.0 and 0.0 <= a_down <= 1.0, params
        assert 0.8 <= a_up + a_down <= 1.2, params


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


def test_load_params_auto_detects_params_json():
    """Ohne Pfad: ./params.json falls vorhanden, sonst Entfernungs-Defaults."""
    import tempfile

    p = Params(tau_minutes=72.0, a_up=0.7, a_down=0.3, offset_cm=-2.5)
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        try:
            os.chdir(d)
            assert load_params(None) == Params()  # keine Datei -> Defaults
            p.save("params.json")
            assert load_params(None) == p  # auto-erkannt
            Params(tau_minutes=50.0).save("other.json")
            assert load_params("other.json").tau_minutes == 50.0  # expliziter Pfad
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("Alle Tests bestanden.")
