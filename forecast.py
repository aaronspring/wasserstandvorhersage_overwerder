#!/usr/bin/env python3
"""Wasserstandsvorhersage fuer Overwerder (Tideelbe, Elbe-km ~605,3).

Holt die BSH-Kurvenvorhersagen fuer Zollenspieker und Hamburg St. Pauli
(Fischmarkt) und interpoliert sie zeitversetzt-gewichtet auf Overwerder.
Optional wird der aktuelle Modellfehler am Messpegel Over abgezogen.

    python forecast.py --params params.json --out out/ --bias-correct
    python forecast.py --explore     # BSH-API-Struktur inspizieren
"""

import argparse
import contextlib
import os

import pandas as pd

from wasserstand_overwerder import model, pegelonline
from wasserstand_overwerder.bsh import BSHClient
from wasserstand_overwerder.plot import plot_forecast


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--params",
        default=None,
        help="params.json aus calibrate.py (Default: ./params.json falls vorhanden)",
    )
    ap.add_argument("--out", default="out", help="Ausgabeverzeichnis")
    ap.add_argument(
        "--bias-correct",
        action="store_true",
        help="mittleres Residuum der letzten 6 h am Pegel Over abziehen",
    )
    ap.add_argument(
        "--explore",
        action="store_true",
        help="nur BSH-API-Struktur ausgeben und beenden",
    )
    args = ap.parse_args()

    client = BSHClient()
    if args.explore:
        client.explore()
        return

    params = model.load_params(args.params)
    print(params.describe())

    print("Lade BSH-Vorhersagen ...")
    up = client.forecast("zollenspieker")
    down = client.forecast("st_pauli")
    print(f"  Zollenspieker: {len(up)} Werte bis {up.index[-1]}")
    print(f"  St. Pauli:     {len(down)} Werte bis {down.index[-1]}")

    target = model.interpolate(up, down, params)

    obs_over = None
    try:
        obs_over = pegelonline.observations("over", start="P2D")
    except Exception as e:  # Beobachtung ist optional
        print(f"Hinweis: Pegel Over nicht verfuegbar ({e})")

    if args.bias_correct and obs_over is not None:
        bias = model.recent_bias_cm(target, obs_over, hours=6.0)
        print(f"Bias-Korrektur: {bias:+.1f} cm (Modell - Beobachtung, letzte 6 h)")
        target = target - bias

    gauge_zero = None
    with contextlib.suppress(Exception):
        gauge_zero = pegelonline.gauge_zero_m_nhn("over")  # i. d. R. -5.00

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "overwerder_forecast.csv")
    df = pd.DataFrame(
        {
            "time_utc": target.index,
            "time_local": target.index.tz_convert("Europe/Berlin"),
            "wasserstand_cm_pnp": target.round(1).values,
        }
    )
    if gauge_zero is not None:
        df["wasserstand_m_nhn"] = (df["wasserstand_cm_pnp"] / 100.0 + gauge_zero).round(
            2
        )
    df.to_csv(csv_path, index=False)

    png_path = os.path.join(args.out, "overwerder_forecast.png")
    plot_forecast(target, up, down, obs_over, png_path, now=pd.Timestamp.now(tz="UTC"))

    nxt = target[target.index >= pd.Timestamp.now(tz="UTC")]
    if len(nxt):
        peak_t, peak_v = nxt.idxmax(), float(nxt.max())
        print(
            f"Naechster Scheitel Overwerder: {peak_v:.0f} cm ueber PNP "
            f"um {peak_t.tz_convert('Europe/Berlin'):%d.%m. %H:%M} Uhr"
        )
    print(f"Geschrieben: {csv_path}\n             {png_path}")


if __name__ == "__main__":
    main()
