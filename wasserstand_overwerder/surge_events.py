"""Pegelkurven der Top-Sturmfluten fuer die Overhaken-Karte (netzfrei).

Ein Klick auf eine Top-10-Linie im Web-Chart zeigt die Karte zum Scheitel des
Ereignisses. Damit Ueberlaufzeiten, laufendes Maximum und Versickerung wie im
echten Verlauf stimmen, braucht die Karte die Over-Kurve davor, nicht nur den
Scheitelwert. Diese Kurven (cm ueber PNP, wie ``data.json``) schreibt
``export_surge_events.py`` nach ``web/public/surge_events.json``.
"""

from __future__ import annotations

import pandas as pd

from .config import (
    STURMFLUT_SCHEITEL_CM,
    STURMFLUT_SCHEITEL_ZEIT,
    SURGE_EVENT_AFTER_H,
    SURGE_EVENT_BEFORE_H,
)

STEP = "10min"
# Gesuchter Scheitel darf so weit vom dokumentierten Zeitpunkt liegen.
PEAK_TOLERANCE = pd.Timedelta(hours=1)


def peak_utc(local: str) -> pd.Timestamp:
    """Scheitelzeit (gesetzliche Zeit Europe/Berlin) als UTC."""
    return pd.Timestamp(local).tz_localize("Europe/Berlin").tz_convert("UTC")


def event_series(
    s: pd.Series,
    peak: pd.Timestamp,
    before_h: float = SURGE_EVENT_BEFORE_H,
    after_h: float = SURGE_EVENT_AFTER_H,
) -> tuple[pd.Series, pd.Timestamp, float]:
    """Ausschnitt um den Scheitel, auf ``STEP`` gemittelt, Scheitel exakt.

    ``s``: minuetliche Over-Reihe (cm ueber PNP, tz-aware UTC). Rueckgabe:
    (Reihe, Scheitelzeit, Scheitelwert); der Scheitel ist das Maximum innerhalb
    ``PEAK_TOLERANCE`` um ``peak`` und bleibt als eigener Stuetzpunkt erhalten,
    damit das Mitteln ihn nicht abflacht.
    """
    win = s[
        (s.index >= peak - pd.Timedelta(hours=before_h))
        & (s.index <= peak + pd.Timedelta(hours=after_h))
    ]
    near = win[
        (win.index >= peak - PEAK_TOLERANCE) & (win.index <= peak + PEAK_TOLERANCE)
    ]
    if near.empty:
        raise ValueError(f"Keine Werte um den Scheitel {peak}")
    t_max = near.idxmax()
    v_max = float(near.max())
    out = win.resample(STEP, origin="start").mean().dropna()
    out = out[
        (out.index < t_max - pd.Timedelta(minutes=5))
        | (out.index > t_max + pd.Timedelta(minutes=5))
    ]
    out.loc[t_max] = v_max
    return out.sort_index(), t_max, v_max


def build_events(s: pd.Series) -> list[dict]:
    """Alle Ereignisse aus ``STURMFLUT_SCHEITEL_*`` fuer ``surge_events.json``."""
    events = []
    for rank, (cm, label) in sorted(STURMFLUT_SCHEITEL_CM.items()):
        series, t_max, v_max = event_series(s, peak_utc(STURMFLUT_SCHEITEL_ZEIT[rank]))
        events.append(
            {
                "rank": rank,
                "label": label,
                "cm": float(cm),
                "peak": t_max.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "peak_cm": round(v_max, 1),
                "series": [
                    [t.strftime("%Y-%m-%dT%H:%M:%SZ"), round(float(v), 1)]
                    for t, v in series.items()
                ],
            }
        )
    return events
