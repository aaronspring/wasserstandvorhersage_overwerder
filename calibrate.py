#!/usr/bin/env python3
"""Kalibriert das Overwerder-Modell an Beobachtungen des Pegels Over.

Holt die letzten N Tage (max. 31) Wasserstaende von PEGELONLINE fuer
Zollenspieker, Hamburg St. Pauli und Over und fittet Laufzeit, Gewichte
und Offset. Ergebnis: params.json (+ Guetemasse auf stdout).

    python calibrate.py --days 30 --out params.json
"""

import argparse

from wasserstand_overwerder import model, pegelonline


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--days", type=int, default=30, help="Kalibrierzeitraum in Tagen (max. 31)"
    )
    ap.add_argument("--out", default="params.json", help="Ausgabedatei")
    args = ap.parse_args()

    start = f"P{min(args.days, 31)}D"
    print(f"Lade Beobachtungen (start={start}) von PEGELONLINE ...")
    up = pegelonline.observations("zollenspieker", start=start)
    down = pegelonline.observations("st_pauli", start=start)
    target = pegelonline.observations("over", start=start)
    print(f"  Zollenspieker: {len(up)}  St. Pauli: {len(down)}  Over: {len(target)}")

    params, metrics = model.calibrate(up, down, target)
    params.save(args.out)

    print(f"\nKalibrierung -> {args.out}")
    if metrics.get("restricted"):
        print(
            "  ACHTUNG: kein plausibler freier Fit — eingeschraenkt kalibriert "
            "(Gewichte auf Entfernungsanteilen, nur tau/Offset aus den Daten)."
        )
    elif metrics.get("rejected"):
        print(f"  {metrics['rejected']} entartete Kandidaten verworfen")
    print(f"  tau (St. Pauli -> Zollenspieker): {params.tau_minutes:.0f} min")
    print(
        f"  Gewichte: a_up={params.a_up:.3f}  a_down={params.a_down:.3f}  "
        f"Offset={params.offset_cm:+.1f} cm"
    )
    print(
        "  Guete gegen Pegel Over: "
        f"RMSE={metrics['rmse_cm']:.1f} cm  MAE={metrics['mae_cm']:.1f} cm  "
        f"r={metrics['corr']:.4f}  (n={metrics['n']})"
    )


if __name__ == "__main__":
    main()
