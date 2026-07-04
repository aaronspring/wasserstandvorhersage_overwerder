#!/usr/bin/env python3
"""Erzeugt data.json fuer das React-Frontend (Wasserstandsvorhersage Overwerder).

Holt die BSH-Vorhersagen (Zollenspieker, St. Pauli), interpoliert sie auf
Overwerder, laedt die Messung am Pegel Over (PEGELONLINE) samt Kennwerten
(MHW/MNW) und schreibt alles als data.json in das Frontend.

    python export_web.py --out web/public
    python export_web.py --params params.json --out web/public --hours-back 36
"""

import argparse
import contextlib
import json
import os

import pandas as pd

from wasserstand_overwerder import config, model, pegelonline, webexport
from wasserstand_overwerder.bsh import BSHClient


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--params",
        default=None,
        help="params.json aus calibrate.py (Default: params.json falls vorhanden)",
    )
    ap.add_argument(
        "--out", default="web/public", help="Zielverzeichnis fuer data.json"
    )
    ap.add_argument(
        "--hours-back", type=int, default=36, help="Stunden Vergangenheit im Chart"
    )
    ap.add_argument(
        "--demo",
        action="store_true",
        help="synthetische Offline-Daten erzeugen (kein Netz; fuer lokalen Dev)",
    )
    args = ap.parse_args()

    params_path = args.params
    if params_path is None and os.path.exists("params.json"):
        params_path = "params.json"
    params = model.Params.load(params_path) if params_path else model.Params()
    print(
        f"Modell: tau={params.tau_minutes:.0f} min, Gewichte="
        f"{tuple(round(w, 3) for w in params.weights())}, "
        f"Offset={params.offset_cm:+.1f} cm"
    )

    now = pd.Timestamp.now(tz="UTC")
    if args.demo:
        print("Demo-Modus: synthetische Offline-Daten (kein Netz).")
        up, down, over = webexport.demo_inputs(now, params.frac)
        refs: dict[str, float] = {"MThw": 746.0, "MTnw": 429.0}
        gauge_zero: float | None = -5.0
    else:
        print("Lade BSH-Vorhersagen ...")
        client = BSHClient()
        up = client.forecast("zollenspieker")
        down = client.forecast("st_pauli")
        print(f"  Zollenspieker: {len(up)} Werte bis {up.index[-1]}")
        print(f"  St. Pauli:     {len(down)} Werte bis {down.index[-1]}")

        over = None
        with contextlib.suppress(Exception):  # Beobachtung ist optional
            over = pegelonline.observations("over", start="P3D")
        if over is None:
            print("Hinweis: Pegel Over (Messung) nicht verfuegbar.")

        refs = {}
        with contextlib.suppress(Exception):  # Kennwerte optional
            refs = pegelonline.characteristic_values("over")

        gauge_zero = None
        with contextlib.suppress(Exception):
            gauge_zero = pegelonline.gauge_zero_m_nhn("over")  # i. d. R. -5.00

    target = model.interpolate(up, down, params)
    payload = webexport.build_payload(
        target=target,
        over=over,
        up=up,
        down=down,
        reference_lines=refs,
        gelaende_cm=config.WASSER_AUF_GELAENDE_OVER_CM,
        gauge_zero_m_nhn=gauge_zero,
        now=now,
        hours_back=args.hours_back,
    )

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "data.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    n = {k: len(v) for k, v in payload["series"].items()}
    print(f"Geschrieben: {out_path}  (Serienlaengen: {n})")


if __name__ == "__main__":
    main()
