"""Netzfreier Test fuer webexport.build_payload (Struktur der data.json)."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_model import synthetic_tide

from wasserstand_overwerder import webexport
from wasserstand_overwerder.model import Params, interpolate


def _scenario(now: pd.Timestamp):
    """BSH-Serien (Vergangenheit + Zukunft) und Over-Messung (nur Vergangenheit)."""
    t0 = now - pd.Timedelta(days=2)
    p = Params()
    down = synthetic_tide(t0, 4, 0.0, 510, 180)  # St. Pauli, laeuft 4 Tage
    up = synthetic_tide(t0, 4, 70.0, 500, 150)  # Zollenspieker
    target = interpolate(up, down, p)
    over = synthetic_tide(t0, 2, 45.0, 505, 165)  # Over: nur bis "jetzt"
    over = over[over.index <= now]
    return target, over, up, down


def test_payload_structure_and_trim():
    now = pd.Timestamp("2026-06-03T00:00:00", tz="UTC")
    target, over, up, down = _scenario(now)
    payload = webexport.build_payload(
        target=target,
        over=over,
        up=up,
        down=down,
        reference_lines={"MHW": 744.3, "MNW": None},
        gauge_zero_m_nhn=-5.0,
        now=now,
        hours_back=36,
    )

    # Pflichtfelder vorhanden
    for key in ("generated_at", "now", "forecast_start", "series", "reference_lines"):
        assert key in payload, key

    # ISO-Zeitstrings, parsebar zu tz-aware UTC
    for key in ("generated_at", "now", "forecast_start"):
        assert pd.to_datetime(payload[key]).tzinfo is not None, key

    # None-Kennwert (MNW) wird verworfen, gueltiger (MHW) bleibt & ist gerundet
    assert payload["reference_lines"] == {"MHW": 744.3}

    # 36-h-Trim: kein Serienpunkt liegt vor now-36h
    window_start = now - pd.Timedelta(hours=36)
    for name, pairs in payload["series"].items():
        assert pairs, f"Serie {name} sollte nicht leer sein"
        first = pd.to_datetime(pairs[0][0])
        assert first >= window_start, (name, first)
        assert isinstance(pairs[0][1], float)

    # Over ist Messung: endet nicht in der Zukunft
    over_last = pd.to_datetime(payload["series"]["over"][-1][0])
    assert over_last <= now

    # forecast_start = letzter Over-Messzeitpunkt
    assert pd.to_datetime(payload["forecast_start"]) == over_last

    # Overwerder-Vorhersage reicht in die Zukunft
    ow_last = pd.to_datetime(payload["series"]["overwerder"][-1][0])
    assert ow_last > now


def test_missing_over_and_refs():
    now = pd.Timestamp("2026-06-03T00:00:00", tz="UTC")
    target, _, up, down = _scenario(now)
    payload = webexport.build_payload(
        target=target,
        over=None,
        up=up,
        down=down,
        reference_lines=None,
        gauge_zero_m_nhn=None,
        now=now,
    )
    # Leere/fehlende Serien werden weggelassen
    assert "over" not in payload["series"]
    assert payload["reference_lines"] == {}
    assert payload["gauge_zero_m_nhn"] is None
    # Ohne Messung: forecast_start faellt auf now zurueck
    assert pd.to_datetime(payload["forecast_start"]) == now


def test_demo_inputs_offline():
    now = pd.Timestamp("2026-06-03T00:00:00", tz="UTC")
    up, down, over = webexport.demo_inputs(now, Params().frac)
    assert over.index[-1] <= now  # Messung nur bis "jetzt"
    assert up.index[-1] > now and down.index[-1] > now  # Vorhersage in Zukunft
    payload = webexport.build_payload(
        target=interpolate(up, down, Params()),
        over=over,
        up=up,
        down=down,
        reference_lines={"MThw": 746.0, "MTnw": 429.0},
        gauge_zero_m_nhn=-5.0,
        now=now,
    )
    assert set(payload["series"]) == {"overwerder", "over", "zollenspieker", "st_pauli"}


def test_requires_tz_aware_now():
    now = pd.Timestamp("2026-06-03T00:00:00", tz="UTC")
    target, over, up, down = _scenario(now)
    try:
        webexport.build_payload(
            target=target, over=over, up=up, down=down, now=pd.Timestamp("2026-06-03")
        )
    except ValueError:
        return
    raise AssertionError("naive now sollte ValueError ausloesen")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("Alle Tests bestanden.")
