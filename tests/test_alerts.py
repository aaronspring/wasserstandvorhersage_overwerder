"""Synthetik-Tests fuer die Alarm-Logik (netzfrei).

Baut eine minuetliche M2-Tide mit einer injizierten Ueberflutung, prueft die
Event-Erkennung ueber der Gelaende-Marke und den Issue-Abgleich (plan): neues
Issue, Stufen-Aenderung, Entwarnung, vorbei. Kein Netz, kein GitHub noetig.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import alerts

M2_MIN = 12.42 * 60.0

# Schwellen wie in config (Over, cm ueber PNP).
THRESHOLDS = {
    "Wasser auf Gelände": 834.0,
    "Sturmflut": 888.0,
    "schwere Sturmflut": 979.0,
    "sehr schwere Sturmflut": 1069.0,
}


def _tide(now: pd.Timestamp, *, peak_cm: float, peak_offset_h: float) -> pd.Series:
    """M2-Tide um `now`, mit einem auf `peak_cm` angehobenen Scheitel `peak_offset_h`
    Stunden nach `now`."""
    t0 = now - pd.Timedelta(hours=12)
    idx = pd.date_range(t0, now + pd.Timedelta(days=3), freq="10min", tz="UTC")
    minutes = (idx - t0).total_seconds().to_numpy() / 60.0
    phase = 2.0 * np.pi * minutes / M2_MIN
    base = 500.0 + 180.0 * (np.cos(phase) + 0.2 * np.cos(2 * phase - 1.0))
    s = pd.Series(base, index=idx)
    # Sturmflut-Bump als Gauss um den gewuenschten Scheitelzeitpunkt.
    center = now + pd.Timedelta(hours=peak_offset_h)
    dt_h = (idx - center).total_seconds().to_numpy() / 3600.0
    s = s + (peak_cm - 680.0) * np.exp(-((dt_h / 3.0) ** 2))
    return s


def test_detect_no_event_below_gelaende():
    now = pd.Timestamp("2026-01-10 00:00", tz="UTC")
    s = _tide(now, peak_cm=700.0, peak_offset_h=14)  # unter 834
    assert alerts.detect_events(s, now, THRESHOLDS) == []


def test_detect_single_gelaende_event():
    now = pd.Timestamp("2026-01-10 00:00", tz="UTC")
    s = _tide(now, peak_cm=860.0, peak_offset_h=14)
    events = alerts.detect_events(s, now, THRESHOLDS)
    assert len(events) == 1
    ev = events[0]
    assert ev.stufe == "Wasser auf Gelände"
    assert ev.peak_time > now
    assert 840.0 <= ev.peak_cm <= 900.0


def test_detect_classifies_sturmflut():
    now = pd.Timestamp("2026-01-10 00:00", tz="UTC")
    s = _tide(now, peak_cm=1000.0, peak_offset_h=14)
    (ev,) = alerts.detect_events(s, now, THRESHOLDS)
    assert ev.stufe == "schwere Sturmflut"  # >= 979


def test_detect_ignores_past_peaks():
    now = pd.Timestamp("2026-01-10 00:00", tz="UTC")
    s = _tide(now, peak_cm=900.0, peak_offset_h=-6)  # Scheitel liegt vor now
    assert alerts.detect_events(s, now, THRESHOLDS) == []


def _event(stufe="Wasser auf Gelände", peak_h=14, peak_cm=860.0):
    now = pd.Timestamp("2026-01-10 00:00", tz="UTC")
    peak = now + pd.Timedelta(hours=peak_h)
    return alerts.Event(
        start=peak - pd.Timedelta(hours=1),
        end=peak + pd.Timedelta(hours=1),
        peak_time=peak,
        peak_cm=peak_cm,
        stufe=stufe,
    )


NOW = pd.Timestamp("2026-01-10 00:00", tz="UTC")


def test_plan_creates_issue_for_new_event():
    (action,) = alerts.plan([_event()], [], NOW, THRESHOLDS)
    assert action.kind == "create"
    assert action.tag is True


def test_plan_touch_when_unchanged():
    ev = _event()
    iss = alerts.OpenIssue(
        number=1, start=ev.start, end=ev.end, peak_time=ev.peak_time, stufe=ev.stufe
    )
    (action,) = alerts.plan([ev], [iss], NOW, THRESHOLDS)
    assert action.kind == "touch"
    assert action.tag is False


def test_plan_comments_on_stufe_change():
    ev = _event(stufe="Sturmflut", peak_cm=900.0)
    iss = alerts.OpenIssue(
        number=1,
        start=ev.start,
        end=ev.end,
        peak_time=ev.peak_time,
        stufe="Wasser auf Gelände",
    )
    (action,) = alerts.plan([ev], [iss], NOW, THRESHOLDS)
    assert action.kind == "change"
    assert action.number == 1
    assert action.prev_stufe == "Wasser auf Gelände"
    assert action.tag is True


def test_plan_retracts_future_event_no_longer_forecast():
    # Offenes Issue mit kuenftigem Scheitel, aber kein aktuelles Event.
    peak = NOW + pd.Timedelta(hours=20)
    iss = alerts.OpenIssue(
        number=7,
        start=peak - pd.Timedelta(hours=1),
        end=peak + pd.Timedelta(hours=1),
        peak_time=peak,
        stufe="Sturmflut",
    )
    (action,) = alerts.plan([], [iss], NOW, THRESHOLDS)
    assert action.kind == "retract"
    assert action.tag is True


def test_plan_closes_passed_event():
    peak = NOW - pd.Timedelta(hours=8)  # Scheitel vorbei
    iss = alerts.OpenIssue(
        number=9,
        start=peak - pd.Timedelta(hours=1),
        end=peak + pd.Timedelta(hours=1),
        peak_time=peak,
        stufe="Wasser auf Gelände",
    )
    (action,) = alerts.plan([], [iss], NOW, THRESHOLDS)
    assert action.kind == "passed"
    assert action.tag is False


def test_plan_matches_drifted_window_to_same_issue():
    # Event driftet leicht (2 h spaeter) -> weiterhin dasselbe Issue, kein neues.
    ev = _event(peak_h=16)
    iss = alerts.OpenIssue(
        number=3,
        start=NOW + pd.Timedelta(hours=13),
        end=NOW + pd.Timedelta(hours=15),
        peak_time=NOW + pd.Timedelta(hours=14),
        stufe=ev.stufe,
    )
    (action,) = alerts.plan([ev], [iss], NOW, THRESHOLDS)
    assert action.kind == "touch"
    assert action.number == 3


def test_plan_ignores_deadband_event_without_issue():
    # Scheitel nur im Halte-Band (830 < Marke 834), kein offenes Issue -> nichts tun.
    ev = _event(stufe=None, peak_cm=830.0)
    assert alerts.plan([ev], [], NOW, THRESHOLDS) == []


def test_plan_keeps_issue_open_when_peak_dips_into_band():
    # Scheitel faellt knapp unter die Marke (831), aber im Band -> Issue bleibt
    # offen (touch), keine Entwarnung.
    ev = _event(stufe=None, peak_cm=831.0)
    iss = alerts.OpenIssue(
        number=5,
        start=ev.start,
        end=ev.end,
        peak_time=ev.peak_time,
        stufe="Wasser auf Gelände",
    )
    (action,) = alerts.plan([ev], [iss], NOW, THRESHOLDS)
    assert action.kind == "touch"
    assert action.event.stufe == "Wasser auf Gelände"


def test_sticky_stufe_hysteresis():
    # Innerhalb des Bandes um eine Grenze bleibt die Stufe haengen ...
    assert alerts.sticky_stufe("Sturmflut", 981.0, THRESHOLDS) == "Sturmflut"
    assert alerts.sticky_stufe("schwere Sturmflut", 977.0, THRESHOLDS) == (
        "schwere Sturmflut"
    )
    # ... erst jenseits des Bandes wird um-/herabgestuft.
    assert alerts.sticky_stufe("Sturmflut", 985.0, THRESHOLDS) == "schwere Sturmflut"
    assert alerts.sticky_stufe("schwere Sturmflut", 973.0, THRESHOLDS) == "Sturmflut"


def test_plan_no_change_on_jitter_across_class_boundary():
    # Scheitel pendelt knapp ueber die schwere-Grenze (981) -> kein Kommentar.
    ev = _event(stufe="schwere Sturmflut", peak_cm=981.0)
    iss = alerts.OpenIssue(
        number=6, start=ev.start, end=ev.end, peak_time=ev.peak_time, stufe="Sturmflut"
    )
    (action,) = alerts.plan([ev], [iss], NOW, THRESHOLDS)
    assert action.kind == "touch"


def test_marker_roundtrip():
    ev = _event(stufe="Sturmflut", peak_cm=901.0)
    body = alerts.issue_body(ev, "aaronspring", gauge_zero_m_nhn=-5.0)
    parsed = alerts.parse_open_issue(42, body)
    assert parsed is not None
    assert parsed.number == 42
    assert parsed.stufe == "Sturmflut"
    assert parsed.peak_time == ev.peak_time


def test_thresholds_and_series_from_payload():
    data = {
        "gelaende_cm": 834.0,
        "sturmflut_lines": [
            {"stufe": "Sturmflut", "cm": 888.0},
            {"stufe": "schwere Sturmflut", "cm": 979.0},
        ],
        "series": {
            "overwerder": [
                ["2026-01-10T00:00:00+00:00", 500.0],
                ["2026-01-10T00:10:00+00:00", 510.0],
            ]
        },
    }
    thr = alerts.thresholds_from_payload(data)
    assert thr["Wasser auf Gelände"] == 834.0
    assert thr["Sturmflut"] == 888.0
    s = alerts.series_from_payload(data)
    assert len(s) == 2
    assert s.index.tz is not None
