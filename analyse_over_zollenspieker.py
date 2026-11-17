#!/usr/bin/env python3
"""Vergleich der Messpegel Over und Zollenspieker waehrend Sturmfluten.

Beide Pegel liegen im Langzeitarchiv (Hugging-Face-Dataset
``aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000``). Zollenspieker
(Elbe-km 598,3) liegt 7 km stromauf von Over (km 605,3) — die Tidewelle laeuft
stromauf, Zollenspieker laeuft Over also **nach**.

Beantwortet zwei Fragen fuer das Vorhersagemodell (``model.interpolate``):

* **Laufzeit:** Wie viele Minuten spaeter tritt der Scheitel in Zollenspieker
  ein — und aendert sich das bei Sturmfluten?
* **Scheitelhoehe:** Um wie viel liegt der Zollenspieker-Scheitel ueber dem von
  Over — bleibt der Zusammenhang bis in den Sturmflut-Bereich linear?

Ausgabe: Kennzahlen auf stdout, Figuren nach ``--out`` (Default ``docs/``).
Braucht Netz (Hugging Face); ``--data PFAD`` nutzt stattdessen eine lokale
Parquet-Datei (Spalten ``time``, ``station``, ``w_cm_pnp``).

    uv sync --extra hf
    uv run python analyse_over_zollenspieker.py   # -> docs/over_zollenspieker_*.png
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
from wasserstand_overwerder.config import (
    ELBE_KM,
    PEGELONLINE_HF_REPO,
    PLAUSIBLE_CM_PNP,
)

TZ = "Europe/Berlin"
C_OVER = "#2a78d6"  # wie plot.C_TARGET
C_ZOLLEN = "#4a3aa7"  # wie plot.C_UP
C_GRID = "#e6e4da"
C_MARK = "#6f6e64"

EVENT_GAP = pd.Timedelta("36h")  # Sturm-Cluster wie in docs/TOP_10_STURMFLUTEN.md
MATCH_TOL = pd.Timedelta("3h")  # max. Abstand zweier zusammengehoeriger Thw
TOP_N = 10
WINDOW = pd.Timedelta("15h")  # halbe Fensterbreite der Ereignis-Kurven


def load_stations(data: str | None) -> dict[str, pd.Series]:
    """Minuetliche Reihen (cm ueber PNP) beider Pegel, tz-aware UTC."""
    lo, hi = PLAUSIBLE_CM_PNP
    if data:
        df = pd.read_parquet(data, columns=["time", "station", "w_cm_pnp"])
    else:
        import pyarrow.dataset as ds
        from huggingface_hub import HfFileSystem

        fs = HfFileSystem()
        files = fs.glob(f"datasets/{PEGELONLINE_HF_REPO}/year=*/*.parquet")
        dataset = ds.dataset(files, filesystem=fs, format="parquet")
        df = dataset.to_table(columns=["time", "station", "w_cm_pnp"]).to_pandas()
    out: dict[str, pd.Series] = {}
    for station, grp in df.groupby("station"):
        grp = grp.sort_values("time")
        s = pd.Series(grp["w_cm_pnp"].to_numpy(), index=pd.DatetimeIndex(grp["time"]))
        if s.index.tz is None:
            s.index = s.index.tz_localize("UTC")
        s = s[(s >= lo) & (s <= hi)]
        out[str(station)] = s[~s.index.duplicated(keep="last")]
    return out


def match_highs(over: pd.Series, zollen: pd.Series) -> pd.DataFrame:
    """Tidehochwasser beider Pegel paaren (naechstes Thw innerhalb MATCH_TOL).

    Rueckgabe je Paar: Scheitelzeit/-hoehe beider Pegel, Hoehendifferenz
    ``dh_cm`` (Zollenspieker - Over) und Laufzeit ``dt_min`` (positiv = der
    Scheitel erreicht Zollenspieker spaeter, wie erwartet).
    """
    o = sturmflut.tidal_highs(over)
    z = sturmflut.tidal_highs(zollen)
    left = pd.DataFrame({"t_over": o.index, "over_cm": o.to_numpy()})
    right = pd.DataFrame({"t_zollen": z.index, "zollen_cm": z.to_numpy()})
    df = pd.merge_asof(
        left,
        right,
        left_on="t_over",
        right_on="t_zollen",
        direction="nearest",
        tolerance=MATCH_TOL,
    ).dropna(subset=["t_zollen"])
    df["dh_cm"] = df["zollen_cm"] - df["over_cm"]
    df["dt_min"] = (df["t_zollen"] - df["t_over"]).dt.total_seconds() / 60.0
    df["local"] = df["t_over"].dt.tz_convert(TZ)
    return df.reset_index(drop=True)


def top_events(pairs: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    """Hoechste Over-Scheitel, greedy entzerrt (ein Scheitel je 36-h-Ereignis)."""
    order = pairs.sort_values("over_cm", ascending=False)
    keep: list[int] = []
    taken: list[pd.Timestamp] = []
    for idx, row in order.iterrows():
        if all(abs(row["t_over"] - t) > EVENT_GAP for t in taken):
            keep.append(idx)
            taken.append(row["t_over"])
        if len(keep) == n:
            break
    events = pairs.loc[keep].sort_values("over_cm", ascending=False)
    return events.reset_index(drop=True)


def print_stats(pairs: pd.DataFrame, top: pd.DataFrame, thr: dict) -> dict:
    """Kennzahlen auf stdout, Zwischenergebnisse fuer die Figuren zurueck."""
    surge = pairs[pairs["over_cm"] >= thr["Sturmflut"]]
    gelaende = pairs[pairs["over_cm"] >= thr["Wasser auf Gelände"]]
    normal = pairs[pairs["over_cm"] < thr["Wasser auf Gelände"]]

    print("=" * 72)
    print("PEGEL OVER (km 605,3) vs. ZOLLENSPIEKER (km 598,3) — Tidehochwasser")
    print("=" * 72)
    print(
        f"Zeitraum      : {pairs['local'].min():%Y-%m-%d} .. "
        f"{pairs['local'].max():%Y-%m-%d}"
    )
    print(f"Thw-Paare     : {len(pairs)} (Zuordnung ≤ {MATCH_TOL})")
    print(
        f"Schwellen Over: Gelände ≥ {thr['Wasser auf Gelände']:.0f} cm, "
        f"Sturmflut ≥ {thr['Sturmflut']:.0f} cm ü. PNP"
    )
    print("-" * 72)
    print(f"{'Kollektiv':<26}{'n':>6}{'Δh (cm)':>12}{'Δt (min)':>12}")
    for name, sub in (
        ("Normaltiden", normal),
        ("Wasser auf Gelände", gelaende),
        ("Sturmflut (BSH)", surge),
    ):
        if sub.empty:
            continue
        print(
            f"{name:<26}{len(sub):>6}"
            f"{sub['dh_cm'].median():>+11.1f}"
            f"{sub['dt_min'].median():>+11.0f}"
        )
    print("  (Δh = Zollenspieker − Over, Δt = Scheitel Zollenspieker später;")
    print("   Angaben sind Mediane.)")
    print("-" * 72)

    fit_all = sturmflut.linear_trend(
        pairs["over_cm"].to_numpy(), pairs["zollen_cm"].to_numpy()
    )
    fit_surge = (
        sturmflut.linear_trend(
            surge["over_cm"].to_numpy(), surge["zollen_cm"].to_numpy()
        )
        if len(surge) > 5
        else None
    )
    print(
        f"Regression alle Thw : Zollen = {fit_all['slope']:.3f}·Over "
        f"{fit_all['intercept']:+.0f}  (R²={fit_all['r'] ** 2:.3f}, n={len(pairs)})"
    )
    if fit_surge:
        print(
            f"Regression Sturmflut: Zollen = {fit_surge['slope']:.3f}·Over "
            f"{fit_surge['intercept']:+.0f}  (R²={fit_surge['r'] ** 2:.3f}, "
            f"n={len(surge)})"
        )
    resid = pairs["zollen_cm"] - (
        fit_all["slope"] * pairs["over_cm"] + fit_all["intercept"]
    )
    print(
        f"Residuum der Gesamt-Regression bei Sturmfluten: "
        f"{resid[pairs['over_cm'] >= thr['Sturmflut']].median():+.1f} cm (Median)"
    )
    print("-" * 72)
    print(f"Top {len(top)} Over-Scheitel (Ereignisse ≥ {EVENT_GAP} entzerrt):")
    print(
        f"{'#':>3}  {'Scheitel Over (Berlin)':<22}{'Over':>7}{'Zollen':>8}"
        f"{'Δh':>7}{'Δt':>7}"
    )
    for i, row in top.iterrows():
        print(
            f"{i + 1:>3}  {row['local']:%Y-%m-%d %H:%M}      "
            f"{row['over_cm']:>7.0f}{row['zollen_cm']:>8.0f}"
            f"{row['dh_cm']:>+7.0f}{row['dt_min']:>+7.0f}"
        )
    print("  (cm ü. PNP; Δt in Minuten)")
    return {"fit_all": fit_all, "fit_surge": fit_surge, "surge": surge}


def _style(ax) -> None:
    ax.grid(True, color=C_GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def _binned_median(pairs: pd.DataFrame, column: str, width: float = 20.0) -> tuple:
    """Median von ``column`` je Hoehenklasse der Over-Scheitel (Breite in cm)."""
    x = pairs["over_cm"].to_numpy()
    bins = np.arange(np.floor(x.min() / width) * width, x.max() + width, width)
    med = pairs.groupby(pd.cut(pairs["over_cm"], bins), observed=True)[column].median()
    return np.array([iv.mid for iv in med.index]), med.to_numpy()


def fig_scatter(pairs, top, thr, stats, out: Path) -> Path:
    """Hoehendifferenz und Laufzeit gegen die Over-Scheitelhoehe."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), dpi=150)
    x = pairs["over_cm"].to_numpy()

    panels = (
        (
            "dh_cm",
            "Δh Scheitel: Zollenspieker − Over (cm)",
            "Scheitelhöhe: Zollenspieker sonst +4 cm,\nbei Extremen unter Over",
            (-40, 40),
        ),
        (
            "dt_min",
            "Δt Scheitel: Zollenspieker − Over (min)",
            "Laufzeit stromauf: ~15 min,\nbei den höchsten Scheiteln länger",
            (-30, 80),
        ),
    )
    for ax, (col, ylabel, title, ylim) in zip(axes, panels, strict=True):
        ax.scatter(x, pairs[col], s=3, color=C_ZOLLEN, alpha=0.18, lw=0)
        ctr, med = _binned_median(pairs, col)
        ax.plot(ctr, med, color=C_OVER, lw=1.8, label="Median je 20 cm")
        ax.scatter(
            top["over_cm"],
            top[col],
            s=26,
            color="#b0272c",
            zorder=4,
            label=f"Top {len(top)} Ereignisse",
        )
        ax.axhline(0, color=C_MARK, lw=0.8)
        for cm, name in (
            (thr["Wasser auf Gelände"], "Gelände"),
            (thr["Sturmflut"], "Sturmflut"),
        ):
            ax.axvline(cm, color=C_MARK, lw=0.8, ls=":")
            ax.annotate(
                name,
                (cm, ylim[1]),
                xytext=(2, -10),
                textcoords="offset points",
                fontsize=7,
                color=C_MARK,
                rotation=90,
            )
        ax.set_xlabel("Scheitel Over (cm ü. PNP)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.set_ylim(*ylim)
        ax.legend(frameon=False, fontsize=8, loc="lower left")
        _style(ax)

    fig.suptitle(
        "Pegel Over vs. Zollenspieker (7 km stromauf), Tidehochwasser 2000–heute",
        fontsize=11,
    )
    fig.tight_layout()
    p = out / "over_zollenspieker_scheitel.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_events(over, zollen, top, thr, out: Path) -> Path:
    """Kurvenvergleich fuer die Top-Ereignisse (Small Multiples)."""
    n = len(top)
    ncol = 5
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(3.0 * ncol, 2.6 * nrow), dpi=150, sharey=True
    )
    for k, ax in enumerate(np.atleast_1d(axes).ravel()):
        if k >= n:
            ax.axis("off")
            continue
        row = top.iloc[k]
        t0, t1 = row["t_over"] - WINDOW, row["t_over"] + WINDOW
        o = over.loc[t0:t1].tz_convert(TZ)
        z = zollen.loc[t0:t1].tz_convert(TZ)
        ax.plot(o.index, o.to_numpy(), color=C_OVER, lw=1.2, label="Over")
        ax.plot(z.index, z.to_numpy(), color=C_ZOLLEN, lw=1.2, label="Zollenspieker")
        ax.axhline(thr["Wasser auf Gelände"], color=C_MARK, lw=0.8, ls=":")
        ax.axvline(row["local"], color=C_OVER, lw=0.8, ls="--")
        ax.set_title(
            f"#{k + 1}  {row['local']:%Y-%m-%d}\n"
            f"Δh {row['dh_cm']:+.0f} cm · Δt {row['dt_min']:+.0f} min",
            fontsize=9,
        )
        ax.set_xticks(
            [
                row["local"] - pd.Timedelta("12h"),
                row["local"],
                row["local"] + pd.Timedelta("12h"),
            ]
        )
        ax.set_xticklabels(["−12 h", "Scheitel", "+12 h"], fontsize=8)
        ax.tick_params(labelsize=8)
        if k % ncol == 0:
            ax.set_ylabel("cm ü. PNP", fontsize=9)
        if k == 0:
            ax.legend(frameon=False, fontsize=8, loc="upper left")
        _style(ax)
    fig.suptitle(
        f"Top {n} Sturmfluten am Pegel Over: Over (blau) und Zollenspieker (violett)\n"
        'gepunktet: „Wasser auf dem Gelände"',
        fontsize=11,
    )
    fig.tight_layout()
    p = out / "over_zollenspieker_ereignisse.png"
    fig.savefig(p)
    plt.close(fig)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--data",
        default=None,
        help="lokale Parquet-Datei (time, station, w_cm_pnp) statt HF-Dataset",
    )
    ap.add_argument("--out", default="docs", help="Ziel-Verzeichnis für Figuren")
    ap.add_argument("--top", type=int, default=TOP_N, help="Anzahl Ereignisse")
    ap.add_argument("--no-figures", action="store_true", help="nur Kennzahlen")
    args = ap.parse_args()

    print("Lade Pegelreihen ...", flush=True)
    series = load_stations(args.data)
    missing = {"over", "zollenspieker"} - set(series)
    if missing:
        raise SystemExit(f"Pegel fehlen im Datensatz: {sorted(missing)}")
    over, zollen = series["over"], series["zollenspieker"]
    print(f"  Over {len(over)}, Zollenspieker {len(zollen)} Minutenwerte", flush=True)
    print(
        f"  Distanz {ELBE_KM['overwerder'] - ELBE_KM['zollenspieker']:.1f} km "
        "(Zollenspieker stromauf)",
        flush=True,
    )

    thr = sturmflut.over_thresholds(
        sturmflut.align_to_stpauli(sturmflut.tidal_highs(over))
    )
    pairs = match_highs(over, zollen)
    top = top_events(pairs, args.top)
    stats = print_stats(pairs, top, thr)

    if not args.no_figures:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        paths = [
            fig_scatter(pairs, top, thr, stats, out),
            fig_events(over, zollen, top, thr, out),
        ]
        print("\nFiguren:")
        for p in paths:
            print(f"  {p}")


if __name__ == "__main__":
    main()
