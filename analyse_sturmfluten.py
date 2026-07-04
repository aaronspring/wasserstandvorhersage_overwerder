#!/usr/bin/env python3
"""EDA der Sturmfluten am Pegel Over (2000-2026): Haeufigkeit, Saisonalitaet, Trend.

Laedt die minuetliche Rohreihe des Pegels Over aus dem Hugging-Face-Dataset
(``aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000``), erkennt die
Tidehochwasser und klassifiziert Sturmfluten nach der **BSH-Nordsee-Definition**.

Die amtlichen Schwellen (BSH-Stufen, Marke "Wasser auf dem Gelaende") beziehen
sich auf den Pegel **St. Pauli**. Da St. Pauli nicht im Langzeitarchiv liegt,
werden die Schwellen ueber Datums-Anker (bekannte Sturmfluten mit amtlichem
St.-Pauli-Scheitel + MThw-Paar) linear auf den Pegel Over uebersetzt
(``sturmflut.align_to_stpauli``).

Beantwortet vier Fragen:

* **Saisonalitaet:** In welchem Monat sind Sturmfluten am wahrscheinlichsten?
* **Haeufigkeit:** Wie viele Sturmfluten pro Sturmflut-Saison (Jul-Jun)?
* **Trend:** Werden Sturmfluten ueber die Jahre haeufiger oder staerker?
* **Gelaende:** Wie oft steht Wasser auf dem Overwerder-Gelaende?

Ausgabe: Kennzahlen auf stdout und Figuren nach ``--out`` (Default ``docs/``).
Braucht Netz (Hugging Face); mit ``--data PFAD`` laesst sich eine lokale
Parquet-Datei (Spalten ``time``, ``w_cm_pnp``) statt des HF-Datasets verwenden.

    uv sync --extra hf
    uv run python analyse_sturmfluten.py            # -> docs/sturmflut_*.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wasserstand_overwerder import sturmflut
from wasserstand_overwerder.config import PEGELONLINE_HF_REPO, PLAUSIBLE_CM_PNP

# Hausfarben (analog plot.py): Gelaende hellblau, Warnstufen orange/rot.
C_BASE = "#2a78d6"
C_GELAENDE = "#7fb9e6"  # Wasser auf dem Gelaende
C_STURM = "#e8a33d"  # Sturmflut
C_SCHWER = "#eb6834"  # schwere Sturmflut
C_SEHR = "#b0272c"  # sehr schwere Sturmflut
C_MThw = "#4a3aa7"
C_GRID = "#e6e4da"
STUFE_FARBE = {
    "Wasser auf Gelände": C_GELAENDE,
    "Sturmflut": C_STURM,
    "schwere Sturmflut": C_SCHWER,
    "sehr schwere Sturmflut": C_SEHR,
}
MONATE = [
    "Jan",
    "Feb",
    "Mär",
    "Apr",
    "Mai",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Okt",
    "Nov",
    "Dez",
]


def load_over(data: str | None) -> pd.Series:
    """Minuetliche Over-Reihe (cm ueber PNP) aus HF-Dataset oder lokaler Datei."""
    lo, hi = PLAUSIBLE_CM_PNP
    if data:
        df = pd.read_parquet(data)
    else:
        import pyarrow.dataset as ds
        from huggingface_hub import HfFileSystem

        fs = HfFileSystem()
        files = fs.glob(f"datasets/{PEGELONLINE_HF_REPO}/year=*/*.parquet")
        dataset = ds.dataset(files, filesystem=fs, format="parquet")
        tbl = dataset.to_table(
            columns=["time", "w_cm_pnp"], filter=ds.field("station") == "over"
        )
        df = tbl.to_pandas()
    df = df.sort_values("time")
    s = pd.Series(df["w_cm_pnp"].to_numpy(), index=pd.DatetimeIndex(df["time"]))
    if s.index.tz is None:
        s.index = s.index.tz_localize("UTC")
    return s[(s >= lo) & (s <= hi)]


def _full_seasons(flood: pd.DataFrame) -> list[int]:
    """Vollstaendig abgedeckte Sturmflut-Saisons (letzte Saison ggf. angebrochen)."""
    last = flood["local"].max()
    last_full = last.year - 1 if last.month < 7 else last.year
    return list(range(2000, last_full))


def print_stats(flood, surges, highs, mthw, thr, fit, out_seasons) -> dict:
    """Kennzahlen auf stdout und als dict fuer die Figuren zurueckgeben."""
    seasons = out_seasons
    print("=" * 68)
    print("STURMFLUTEN & GELÄNDE-ÜBERFLUTUNG AM PEGEL OVER (Overwerder)")
    print("=" * 68)
    print(
        f"Zeitraum          : {highs.index.min():%Y-%m-%d} .. "
        f"{highs.index.max():%Y-%m-%d}"
    )
    print(f"Tidehochwasser    : {len(highs)} erkannt (~2/Tag)")
    print(f"MThw Over         : {mthw:.0f} cm ü. PNP = {mthw / 100 - 5:.2f} m NHN")
    print(
        f"Ausrichtung Over↔St. Pauli: Over = {fit['slope']:.3f}·StP "
        f"{fit['intercept']:+.0f}  (R²={fit['r'] ** 2:.3f}, n={int(fit['n'])})"
    )
    print("Amtliche St.-Pauli-Schwellen → Over cm ü. PNP:")
    print(f"  Wasser auf Gelände (NN+3,0 m) : Over ≥ {thr['Wasser auf Gelände']:.0f}")
    print(f"  Sturmflut (MThw+1,5 m)        : Over ≥ {thr['Sturmflut']:.0f}")
    print(f"  schwere (MThw+2,5 m)          : Over ≥ {thr['schwere Sturmflut']:.0f}")
    print(
        f"  sehr schwere (MThw+3,5 m)     : Over ≥ {thr['sehr schwere Sturmflut']:.0f}"
    )
    print("-" * 68)

    span_yr = (highs.index.max() - highs.index.min()).days / 365.25
    g_tides = len(flood)
    g_events = int(flood["event"].nunique())
    only_g = int((flood["stufe"] == "Wasser auf Gelände").sum())
    med_over = float((flood["peak_cm"] - thr["Wasser auf Gelände"]).median())
    ev_year = flood.groupby("year")["event"].nunique()
    ev_year = ev_year.reindex(range(2000, highs.index.max().year + 1), fill_value=0)
    ev_month = (
        flood.groupby("month")["event"].nunique().reindex(range(1, 13), fill_value=0)
    )
    win_ev = int(ev_month.reindex([10, 11, 12, 1, 2, 3]).sum())
    print(
        f"\nWASSER AUF DEM GELÄNDE (Over ≥ {thr['Wasser auf Gelände']:.0f} cm, "
        "St. Pauli NN+3,0 m):"
    )
    print(
        f"  {g_tides} Thw in {g_events} Ereignissen ⇒ ≈ {g_events / span_yr:.0f} "
        f"Ereignisse/Jahr ({g_tides / span_yr:.0f} Tiden/Jahr)"
    )
    print(
        f"  davon {only_g} Tiden nur knapp über der Marke (< Sturmflut), "
        f"Median nur {med_over:.0f} cm darüber"
    )
    print(
        f"  {win_ev}/{int(ev_month.sum())} Ereignisse im Winterhalbjahr (Okt–Mär); "
        "im Sommer (Mai–Aug) fast nie"
    )
    print("  Ereignisse/Jahr je Monat (Mittel):")
    for m in (12, 1, 2, 11, 10, 3):
        print(f"    {MONATE[m - 1]}: {ev_month[m] / span_yr:.1f}")

    print("\nSTURMFLUTEN (Klassenverteilung, aligned):")
    vc = surges["stufe"].value_counts().reindex(sturmflut.KLASSEN, fill_value=0)
    for k in sturmflut.KLASSEN:
        print(f"  {k:24s}: {vc[k]:4d}")
    print(f"  {'gesamt':24s}: {len(surges):4d}")

    print("\nSAISONALITÄT — Sturmflut-Tiden je Monat:")
    mc = surges.groupby("month").size().reindex(range(1, 13), fill_value=0)
    for m in range(1, 13):
        print(f"  {MONATE[m - 1]}: {mc[m]:3d} {'█' * mc[m]}")
    win = mc.reindex([10, 11, 12, 1, 2, 3]).sum()
    print(f"  -> Okt-Mär: {win}/{len(surges)} ({100 * win / len(surges):.0f} %)")

    print("\nHÄUFIGKEIT — Sturmflut-Tiden je Saison (Jul-Jun):")
    sc = surges.groupby("season").size().reindex(seasons, fill_value=0)
    print(
        f"  Mittel {sc.mean():.1f}/Saison  (min {sc.min()}, max {sc.max()} "
        f"in {sc.idxmax()}/{sc.idxmax() + 1})"
    )
    tr = sturmflut.linear_trend(np.asarray(seasons), sc.to_numpy())
    sig = "signifikant" if tr["p"] < 0.05 else "NICHT signifikant"
    print(
        f"  Trend {tr['slope'] * 10:+.2f}/Dekade (r={tr['r']:.2f}, "
        f"p={tr['p']:.2f}) -> {sig}"
    )

    print("\nINTENSITÄT — Trend des Saison-Höchstscheitels:")
    amax = surges.groupby("season")["peak_cm"].max().reindex(seasons).dropna()
    tri = sturmflut.linear_trend(amax.index.to_numpy(), amax.to_numpy())
    sig_i = "signifikant" if tri["p"] < 0.05 else "NICHT signifikant"
    print(
        f"  {tri['slope'] * 10:+.1f} cm/Dekade (r={tri['r']:.2f}, "
        f"p={tri['p']:.2f}) -> {sig_i}"
    )
    half = len(seasons) // 2
    sev = surges[surges["stufe"] != sturmflut.KLASSEN[0]]
    sev_c = sev.groupby("season").size().reindex(seasons, fill_value=0)
    print(
        f"  schwere+ Sturmfluten: 1. Hälfte {sev_c.iloc[:half].sum()} | "
        f"2. Hälfte {sev_c.iloc[half:].sum()}"
    )

    print("\nHINTERGRUND — MThw-Drift (Mittel aller Thw/Jahr):")
    ym = sturmflut.annual_mthw(highs)
    ym = ym.loc[(ym.index >= 2000) & (ym.index <= highs.index.max().year - 1)]
    trm = sturmflut.linear_trend(ym.index.to_numpy(), ym.to_numpy())
    sig_m = "signifikant" if trm["p"] < 0.05 else "NICHT signifikant"
    print(
        f"  {trm['slope'] * 10:+.1f} cm/Dekade (r={trm['r']:.2f}, "
        f"p={trm['p']:.3f}) -> {sig_m}"
    )
    print("=" * 68)

    return {
        "seasons": seasons,
        "season_counts": sc,
        "month_counts": surges.pivot_table(
            index="month", columns="stufe", aggfunc="size", fill_value=0
        ).reindex(index=range(1, 13), columns=sturmflut.KLASSEN, fill_value=0),
        "annual_max": amax,
        "annual_mthw": ym,
        "gelaende_events_year": ev_year,
        "gelaende_events_month": ev_month / span_yr,
        "gelaende_events_per_yr": g_events / span_yr,
        "trend_freq": tr,
        "trend_int": tri,
        "trend_mthw": trm,
    }


def _style(ax) -> None:
    ax.grid(True, color=C_GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def make_figures(surges, flood, highs, thr, stats, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    # 1) Saisonalitaet: gestapelte Balken je Monat/Klasse
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    mc = stats["month_counts"]
    bottom = np.zeros(12)
    for k in sturmflut.KLASSEN:
        ax.bar(
            range(1, 13),
            mc[k].to_numpy(),
            bottom=bottom,
            color=STUFE_FARBE[k],
            label=k,
            width=0.8,
        )
        bottom += mc[k].to_numpy()
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(MONATE)
    ax.set_ylabel("Sturmflut-Tiden 2000–2026")
    ax.set_title(
        "Saisonalität der Sturmfluten am Pegel Over\n"
        "95 % im Winterhalbjahr (Okt–Mär), Höhepunkt Dez–Feb",
        fontsize=11,
    )
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    _style(ax)
    fig.tight_layout()
    p = out / "sturmflut_saisonalitaet.png"
    fig.savefig(p)
    plt.close(fig)
    paths.append(p)

    # 2) Haeufigkeit je Saison + Trendlinie
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    sc = stats["season_counts"]
    ax.bar(sc.index, sc.to_numpy(), color=C_BASE, width=0.75, alpha=0.9)
    tr = stats["trend_freq"]
    xs = np.asarray(sc.index, dtype=float)
    ax.plot(
        xs,
        tr["slope"] * xs + tr["intercept"],
        color=C_SCHWER,
        lw=2,
        label=f"Trend {tr['slope'] * 10:+.1f}/Dekade (p={tr['p']:.2f}, n. s.)",
    )
    ax.axhline(
        sc.mean(), color="#6f6e64", lw=1, ls=":", label=f"Mittel {sc.mean():.1f}/Saison"
    )
    ax.set_xlabel("Sturmflut-Saison (Jul–Jun, nach Startjahr)")
    ax.set_ylabel("Sturmflut-Tiden je Saison")
    ax.set_title(
        "Häufigkeit je Saison — hohe Streuung, kein robuster Trend", fontsize=11
    )
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax)
    fig.tight_layout()
    p = out / "sturmflut_haeufigkeit.png"
    fig.savefig(p)
    plt.close(fig)
    paths.append(p)

    # 3) Intensitaet: jede Sturmflut-Tide + Schwellen + Rekorde
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    yrs = surges["local"].dt.year + (surges["local"].dt.dayofyear / 365.25)
    for k in sturmflut.KLASSEN:
        m = surges["stufe"] == k
        ax.scatter(
            yrs[m],
            surges["peak_cm"][m],
            s=22,
            color=STUFE_FARBE[k],
            label=k,
            zorder=3,
            edgecolor="white",
            lw=0.3,
        )
    lines = [
        (thr["Wasser auf Gelände"], "Wasser auf Gelände (St. Pauli NN+3,0 m)"),
        (thr["Sturmflut"], "Sturmflut (MThw+1,5 m)"),
        (thr["schwere Sturmflut"], "schwere (+2,5 m)"),
        (thr["sehr schwere Sturmflut"], "sehr schwere (+3,5 m)"),
    ]
    for lvl, txt in lines:
        ax.axhline(lvl, color="#8a8878", lw=0.7, ls="--")
        ax.annotate(
            txt,
            xy=(0.005, lvl),
            xycoords=("axes fraction", "data"),
            fontsize=7,
            color="#6f6e64",
            va="bottom",
        )
    for label, yr, cm in (
        ("Xaver 2013", 2013.93, 1114),
        ("Zeynep 2022", 2022.13, 1110),
    ):
        ax.annotate(
            label,
            xy=(yr, cm),
            xytext=(yr - 4.2, cm - 32),
            fontsize=7.5,
            color=C_SEHR,
            ha="center",
            arrowprops={"arrowstyle": "->", "color": C_SEHR, "lw": 0.7},
        )
    ax.set_ylabel("Scheitel [cm über PNP]")
    ax.set_title("Intensität jeder Sturmflut-Tide (2000–2026)", fontsize=11, pad=22)
    ax.legend(
        frameon=False, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3
    )
    _style(ax)
    fig.tight_layout()
    p = out / "sturmflut_intensitaet.png"
    fig.savefig(p)
    plt.close(fig)
    paths.append(p)

    # 4) MThw-Drift (Hintergrundpegel)
    fig, ax = plt.subplots(figsize=(9, 4.0), dpi=150)
    ym = stats["annual_mthw"]
    ax.plot(ym.index, ym.to_numpy(), color=C_MThw, marker="o", ms=3, lw=1.4)
    trm = stats["trend_mthw"]
    xs = np.asarray(ym.index, dtype=float)
    sig = "p<0,05" if trm["p"] < 0.05 else f"p={trm['p']:.2f}"
    ax.plot(
        xs,
        trm["slope"] * xs + trm["intercept"],
        color=C_SCHWER,
        lw=2,
        label=f"Trend {trm['slope'] * 10:+.1f} cm/Dekade ({sig})",
    )
    ax.set_ylabel("MThw [cm über PNP]")
    ax.set_title(
        "Hintergrund-Tidehochwasser (MThw) — langsamer Anstieg\n"
        "hebt die Basis, von der jede Sturmflut startet",
        fontsize=11,
    )
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax)
    fig.tight_layout()
    p = out / "sturmflut_mthw_drift.png"
    fig.savefig(p)
    plt.close(fig)
    paths.append(p)

    # 5) Wasser auf dem Gelaende: Haeufigkeit je Jahr (links) + Saisonalitaet (rechts)
    fig, (axa, axb) = plt.subplots(
        1, 2, figsize=(10.5, 4.2), dpi=150, gridspec_kw={"width_ratios": [1.7, 1]}
    )
    ey = stats["gelaende_events_year"]
    mean_ev = stats["gelaende_events_per_yr"]
    axa.bar(ey.index, ey.to_numpy(), color=C_GELAENDE, width=0.8)
    axa.axhline(
        mean_ev,
        color="#6f6e64",
        lw=1,
        ls=":",
        label=f"Mittel {mean_ev:.0f} Ereignisse/Jahr",
    )
    axa.set_ylabel("Überflutungs-Ereignisse je Jahr")
    axa.set_xlabel("Jahr")
    axa.legend(frameon=False, fontsize=8, loc="upper left")
    _style(axa)

    em = stats["gelaende_events_month"]
    axb.bar(range(1, 13), em.to_numpy(), color=C_GELAENDE, width=0.8)
    axb.set_xticks(range(1, 13))
    axb.set_xticklabels([m[0] for m in MONATE])
    axb.set_ylabel("Ereignisse/Jahr je Monat")
    axb.set_xlabel("Monat")
    _style(axb)

    fig.suptitle(
        "Wie oft steht Wasser auf dem Overwerder-Gelände? "
        f"(Over ≥ {thr['Wasser auf Gelände']:.0f} cm ü. PNP = St. Pauli "
        f"NN+3,0 m)\n≈ {mean_ev:.0f} Ereignisse/Jahr, fast nur Okt–Mär "
        "— meist knapp über der Marke, kein Sturmflut-Niveau",
        fontsize=10.5,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    p = out / "sturmflut_gelaende.png"
    fig.savefig(p)
    plt.close(fig)
    paths.append(p)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--data",
        default=None,
        help="lokale Parquet-Datei (time, w_cm_pnp) statt HF-Dataset",
    )
    ap.add_argument("--out", default="docs", help="Ziel-Verzeichnis für Figuren")
    ap.add_argument("--no-figures", action="store_true", help="nur Kennzahlen")
    args = ap.parse_args()

    print("Lade Over-Reihe ...", flush=True)
    s = load_over(args.data)
    print(f"  {len(s)} Minutenwerte", flush=True)
    highs = sturmflut.tidal_highs(s)
    mthw = sturmflut.mean_high_water(highs)
    fit = sturmflut.align_to_stpauli(highs)
    thr = sturmflut.over_thresholds(fit)
    flood = sturmflut.flood_tides(highs, thr).sort_index()
    # Ereignis-Cluster: Scheitel < 36 h auseinander = ein Ueberflutungsereignis.
    gap = flood.index.to_series().diff() > pd.Timedelta("36h")
    flood["event"] = gap.cumsum()
    surges = flood[flood["stufe"] != "Wasser auf Gelände"].copy()
    seasons = _full_seasons(flood)
    stats = print_stats(flood, surges, highs, mthw, thr, fit, seasons)

    if not args.no_figures:
        paths = make_figures(surges, flood, highs, thr, stats, Path(args.out))
        print("\nFiguren:")
        for p in paths:
            print(f"  {p}")


if __name__ == "__main__":
    main()
