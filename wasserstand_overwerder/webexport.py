"""Assemblierung der Web-Datendatei (data.json) fuer das React-Frontend.

Reine, netzfreie Aufbereitung: nimmt fertige Zeitreihen (cm ueber PNP,
tz-aware UTC-Index) und formt sie in ein JSON-serialisierbares Dict. Das
Frontend laedt genau diese Struktur und rendert daraus den Chart.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Reihenfolge/Schluessel der Serien im data.json (Frontend erwartet diese Keys).
SERIES_KEYS = ("overwerder", "over", "zollenspieker", "st_pauli")


def demo_inputs(
    now: pd.Timestamp, frac: float, *, days_past: int = 2, days_future: int = 5
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Synthetische Tidekurven (Zollenspieker, St. Pauli, Over) fuer Offline-Dev.

    Kein Netz noetig: erzeugt eine asymmetrische M2-Tide (mit Obertiden), damit
    `export_web.py --demo` ohne BSH/PEGELONLINE ein realistisches data.json baut.
    """
    m2 = 12.42 * 60.0  # M2-Periode in Minuten
    t0 = (now - pd.Timedelta(days=days_past)).floor("h")
    end = now + pd.Timedelta(days=days_future)
    idx = pd.date_range(t0, end, freq="10min", tz="UTC")
    minutes = (idx - t0).total_seconds().to_numpy() / 60.0

    def tide(lag: float, mean: float, amp: float) -> pd.Series:
        phase = 2.0 * np.pi * (minutes - lag) / m2
        shape = (
            np.cos(phase)
            + 0.25 * np.cos(2.0 * phase - 1.0)
            + 0.10 * np.cos(3.0 * phase + 0.5)
        )
        spring = 1.0 + 0.15 * np.sin(2.0 * np.pi * minutes / (14.77 * 24 * 60))
        return pd.Series(mean + amp * spring * shape, index=idx)

    down = tide(0.0, 510, 180)  # St. Pauli fuehrt
    up = tide(70.0, 500, 150)  # Zollenspieker laeuft nach
    over = tide(70.0 * (1.0 - frac), 505, 165)  # Over dazwischen
    return up, down, over[over.index <= now]  # Messung nur bis "jetzt"


def _pairs(s: pd.Series | None, start: pd.Timestamp, step_minutes: int) -> list[list]:
    """Serie ab `start` auf ein `step_minutes`-Raster gemittelt als Liste
    von [ISO-UTC-Zeit, Wert(1 Dezimale)].

    Das Rastern haelt data.json schlank (1-min-Kurven -> ~10-min-Punkte), fuer
    Tidekurven (Periode ~12,4 h) optisch unkritisch.
    """
    if s is None or len(s) == 0:
        return []
    s = s.sort_index()
    if step_minutes and step_minutes > 0:
        s = s.resample(f"{step_minutes}min").mean().dropna()
    s = s[s.index >= start]
    return [
        [t.tz_convert("UTC").isoformat(), round(float(v), 1)]
        for t, v in s.items()
        if pd.notna(v)
    ]


def build_payload(
    *,
    target: pd.Series,
    over: pd.Series | None,
    up: pd.Series,
    down: pd.Series,
    reference_lines: dict[str, float] | None = None,
    gauge_zero_m_nhn: float | None = None,
    now: pd.Timestamp,
    hours_back: int = 36,
    step_minutes: int = 10,
) -> dict:
    """Baut das data.json-Dict.

    target: Vorhersage Overwerder; over: Messung Pegel Over (optional);
    up/down: BSH-Vorhersagen Zollenspieker/St. Pauli. Alle in cm ueber PNP,
    Index tz-aware UTC. now: Bezugszeitpunkt (tz-aware UTC). step_minutes:
    Zeitraster fuer die Ausgabe (0 = kein Rastern).
    """
    if now.tzinfo is None:
        raise ValueError("now muss tz-aware (UTC) sein")
    window_start = now - pd.Timedelta(hours=hours_back)

    series = {
        "overwerder": _pairs(target, window_start, step_minutes),
        "over": _pairs(over, window_start, step_minutes),
        "zollenspieker": _pairs(up, window_start, step_minutes),
        "st_pauli": _pairs(down, window_start, step_minutes),
    }
    series = {k: v for k, v in series.items() if v}

    # Beginn des Vorhersageanteils: Ende der Over-Messreihe (so, wie sie im Chart
    # erscheint), sonst der Bezugszeitpunkt selbst.
    if series.get("over"):
        forecast_start = pd.to_datetime(series["over"][-1][0])
    else:
        forecast_start = now

    refs = {
        k: round(float(v), 1)
        for k, v in (reference_lines or {}).items()
        if v is not None
    }

    return {
        "generated_at": now.tz_convert("UTC").isoformat(),
        "now": now.tz_convert("UTC").isoformat(),
        "forecast_start": forecast_start.tz_convert("UTC").isoformat(),
        "units": "cm ueber PNP",
        "gauge_zero_m_nhn": (
            round(float(gauge_zero_m_nhn), 2) if gauge_zero_m_nhn is not None else None
        ),
        "hours_back": hours_back,
        "reference_lines": refs,
        "series": series,
    }
