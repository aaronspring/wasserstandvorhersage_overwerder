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
C_UP = "#4a3aa7"      # Zollenspieker
C_DOWN = "#eb6834"    # St. Pauli
C_OBS = "#6f6e64"


def _local(s: pd.Series) -> pd.Series:
    return s.tz_convert(TZ)


def plot_forecast(target: pd.Series, up: pd.Series, down: pd.Series,
                  obs_over: pd.Series | None, out_png: str,
                  now: pd.Timestamp | None = None) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)

    ax.plot(_local(up).index, _local(up).values, color=C_UP, lw=1.2,
            alpha=0.8, label="BSH-Vorhersage Zollenspieker (km 598,3)")
    ax.plot(_local(down).index, _local(down).values, color=C_DOWN, lw=1.2,
            alpha=0.8, label="BSH-Vorhersage St. Pauli (km 623,1)")
    ax.plot(_local(target).index, _local(target).values, color=C_TARGET,
            lw=2.4, label="Vorhersage Overwerder (km 605,3)")
    if obs_over is not None and len(obs_over):
        ax.plot(_local(obs_over).index, _local(obs_over).values, color=C_OBS,
                lw=1.4, ls="--", label="Beobachtung Pegel Over")

    if now is not None:
        ax.axvline(now.tz_convert(TZ), color="#8a8878", lw=1, ls=":")
        ax.annotate("jetzt", xy=(now.tz_convert(TZ), 0.02),
                    xycoords=("data", "axes fraction"),
                    fontsize=8, color="#6f6e64", ha="left")

    ax.set_ylabel("Wasserstand [cm über PNP]  (PNP = NHN − 5,00 m)")
    ax.set_title("Wasserstandsvorhersage Overwerder Bogen 79 (Tideelbe)")
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
