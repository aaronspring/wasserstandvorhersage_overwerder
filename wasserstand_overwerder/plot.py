"""Ergebnis-Plot: Vorhersage Overwerder + Stuetzpegel + juengste Beobachtung."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

TZ = "Europe/Berlin"

# Farben: Zielserie blau, Stuetzpegel violett/orange, Beobachtung grau
C_TARGET = "#2a78d6"
C_UP = "#4a3aa7"  # Zollenspieker
C_DOWN = "#eb6834"  # St. Pauli
C_OBS = "#6f6e64"
C_SURGE = "#9ecbf0"  # helles Blau (abgeleitet von C_TARGET) fuer Sturmflut-Marken

# Historische Sturmflut-Scheitel am Pegel Over (cm ueber PNP), Raenge 1/3/5/10.
# Quelle und Methodik: docs/TOP_10_STURMFLUTEN.md
SURGE_DOC = "docs/TOP_10_STURMFLUTEN.md"
SURGE_DOC_URL = (
    "https://github.com/aaronspring/wasserstandvorhersage_overwerder/"
    "blob/main/docs/TOP_10_STURMFLUTEN.md"
)
STURMFLUT_SCHEITEL_CM = {
    1: (1114, "Xaver 2013"),
    3: (1067, "Tilo 2007"),
    5: (1060, "Dez. 2023"),
    10: (1008, "Emma 2008"),
}
# Sturmflut-Marken nur einblenden, wenn die Vorhersage ihnen nahekommt: eine
# Marke wird gezeigt, sobald der Datenscheitel bis auf diesen Abstand (cm)
# heranreicht. So wird der Plot bei Normaltiden nicht durch weit oben liegende
# Linien gestaucht (Proximity-Gating).
SURGE_PROXIMITY_CM = 120.0


def _local(s: pd.Series) -> pd.Series:
    return s.tz_convert(TZ)


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
            line.set_url(SURGE_DOC_URL)  # klickbar in SVG-Ausgaben
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
            f"Sturmflut-Marken: {SURGE_DOC}",
            xy=(0.995, 0.02),
            xycoords="axes fraction",
            fontsize=6.5,
            color=C_SURGE,
            ha="right",
            va="bottom",
            url=SURGE_DOC_URL,
        )

    ax.set_ylabel("Wasserstand [cm über PNP]  (PNP = NHN − 5,00 m)")
    ax.set_title("Wasserstandsvorhersage Overwerder (Tideelbe)")
    ax.grid(True, color="#e6e4da", lw=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m. %H:%M", tz=None))
    fig.autofmt_xdate()
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)
