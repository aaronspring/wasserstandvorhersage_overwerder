"""Ergebnis-Plot: Vorhersage Overwerder + Stuetzpegel + juengste Beobachtung."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .config import STURMFLUT_DOC, STURMFLUT_DOC_URL, STURMFLUT_SCHEITEL_CM

TZ = "Europe/Berlin"

# Farben: Zielserie blau, Stuetzpegel violett/orange, Beobachtung grau
C_TARGET = "#2a78d6"
C_UP = "#4a3aa7"  # Zollenspieker
C_DOWN = "#eb6834"  # St. Pauli
C_OBS = "#6f6e64"
C_SURGE = "#9ecbf0"  # helles Blau (abgeleitet von C_TARGET) fuer Sturmflut-Marken

# Sturmflut-Scheitel (Raenge 1/3/5/10) samt Doku-Verweis stehen in config.py.
# Sturmflut-Marken nur einblenden, wenn die Vorhersage ihnen nahekommt: eine
# Marke wird gezeigt, sobald der Datenscheitel bis auf diesen Abstand (cm)
# heranreicht. So wird der Plot bei Normaltiden nicht durch weit oben liegende
# Linien gestaucht (Proximity-Gating).
SURGE_PROXIMITY_CM = 120.0


def _local(s: pd.Series) -> pd.Series:
    return s.tz_convert(TZ)


def _tide_extrema(
    target: pd.Series, now: pd.Timestamp | None
) -> list[tuple[pd.Timestamp, float, bool]]:
    """Naechste Tide-Scheitel (Hoch-/Niedrigwasser) der Zielserie.

    Liefert je bis zu zwei Flut- (lokales Maximum) und Ebbe-Scheitel (lokales
    Minimum) ab ``now``, chronologisch sortiert. Rueckgabe je Eintrag:
    ``(zeitpunkt, wert_cm, ist_flut)``.
    """
    if target is None or len(target) < 3:
        return []
    s = target.dropna()
    if len(s) < 3:
        return []
    vals = s.values
    idx = s.index
    highs: list[tuple[pd.Timestamp, float, bool]] = []
    lows: list[tuple[pd.Timestamp, float, bool]] = []
    for i in range(1, len(vals) - 1):
        if now is not None and idx[i] < now:
            continue
        if vals[i] >= vals[i - 1] and vals[i] > vals[i + 1]:
            highs.append((idx[i], float(vals[i]), True))
        elif vals[i] <= vals[i - 1] and vals[i] < vals[i + 1]:
            lows.append((idx[i], float(vals[i]), False))
    extrema = highs[:2] + lows[:2]
    extrema.sort(key=lambda e: e[0])
    return extrema


def plot_forecast(
    target: pd.Series,
    up: pd.Series,
    down: pd.Series,
    obs_over: pd.Series | None,
    out_png: str,
    now: pd.Timestamp | None = None,
    show_surges: bool = True,
) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)

    ax.plot(
        _local(up).index,
        _local(up).values,
        color=C_UP,
        lw=1.2,
        alpha=0.8,
        label="BSH-Vorhersage Zollenspieker (km 598,3)",
    )
    ax.plot(
        _local(down).index,
        _local(down).values,
        color=C_DOWN,
        lw=1.2,
        alpha=0.8,
        label="BSH-Vorhersage St. Pauli (km 623,1)",
    )
    ax.plot(
        _local(target).index,
        _local(target).values,
        color=C_TARGET,
        lw=2.4,
        label="Vorhersage Overwerder (km 605,3)",
    )
    if obs_over is not None and len(obs_over):
        ax.plot(
            _local(obs_over).index,
            _local(obs_over).values,
            color=C_OBS,
            lw=1.4,
            ls="--",
            label="Beobachtung Pegel Over",
        )

    if now is not None:
        ax.axvline(now.tz_convert(TZ), color="#8a8878", lw=1, ls=":")
        ax.annotate(
            "jetzt",
            xy=(now.tz_convert(TZ), 0.02),
            xycoords=("data", "axes fraction"),
            fontsize=8,
            color="#6f6e64",
            ha="left",
        )

    # Proximity-Gating: nur Marken zeigen, denen der Datenscheitel nahekommt,
    # damit weit oben liegende Linien den Plot bei Normaltiden nicht stauchen.
    data_max = max(
        (
            float(s.max())
            for s in (up, down, target, obs_over)
            if s is not None and len(s)
        ),
        default=float("-inf"),
    )
    surges = [
        (cm, rank, storm)
        for rank, (cm, storm) in STURMFLUT_SCHEITEL_CM.items()
        if cm <= data_max + SURGE_PROXIMITY_CM
    ]

    if show_surges and surges:
        # nach Hoehe sortiert; Labels mit Mindestabstand entzerren (dicht
        # beieinanderliegende Marken wie #3/#5 wuerden sich sonst ueberlagern).
        label_gap_cm = 26
        last_label = None
        for cm, rank, storm in sorted(surges):
            line = ax.axhline(cm, color=C_SURGE, lw=0.8, zorder=1)
            line.set_url(STURMFLUT_DOC_URL)  # klickbar in SVG-Ausgaben
            label_y = cm if last_label is None else max(cm, last_label + label_gap_cm)
            last_label = label_y
            ax.annotate(
                f"Sturmflut #{rank} ({storm}): {cm} cm",
                xy=(0.995, label_y),
                xycoords=("axes fraction", "data"),
                xytext=(0, 1),
                textcoords="offset points",
                fontsize=7,
                color=C_SURGE,
                ha="right",
                va="bottom",
            )
        # Quelle klein unten rechts vermerken (Klick-Link in SVG-Ausgaben).
        ax.annotate(
            f"Sturmflut-Marken: {STURMFLUT_DOC}",
            xy=(0.995, 0.02),
            xycoords="axes fraction",
            fontsize=6.5,
            color=C_SURGE,
            ha="right",
            va="bottom",
            url=STURMFLUT_DOC_URL,
        )

    # Naechste Tide-Scheitel (2x Flut / 2x Ebbe) als Textbox einblenden.
    extrema = _tide_extrema(target, now)
    if extrema:
        lines = ["Nächste Scheitel Overwerder:"]
        for t, cm, is_high in extrema:
            kind = "Flut " if is_high else "Ebbe "
            lines.append(f"{kind} {t.tz_convert(TZ):%d.%m. %H:%M}  {cm:.0f} cm")
        ax.annotate(
            "\n".join(lines),
            xy=(0.995, 0.97),
            xycoords="axes fraction",
            ha="right",
            va="top",
            fontsize=7.5,
            color=C_TARGET,
            bbox={
                "boxstyle": "round",
                "fc": "white",
                "ec": C_TARGET,
                "lw": 0.6,
                "alpha": 0.85,
            },
        )

    ax.set_ylabel("Wasserstand [cm über PNP]  (PNP = NHN − 5,00 m)")
    ax.set_title("Wasserstandsvorhersage Overwerder (Tideelbe)")
    ax.grid(True, color="#e6e4da", lw=0.6)
    ax.grid(True, which="minor", color="#f0eee6", lw=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    # Ticks alle 3 h (minor, unbeschriftet), Labels alle 6 h (major).
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 6), tz=TZ))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 3), tz=TZ))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m. %H:%M", tz=TZ))
    fig.autofmt_xdate()
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)
