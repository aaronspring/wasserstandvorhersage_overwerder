#!/usr/bin/env python3
"""Baut das GESAMTE jaehrlich partitionierte Parquet-Archiv (einmaliger Backfill).

Quelle: PEGELONLINE-Langzeitarchiv ("Download langfristiger Wasserstaende
(Rohdaten) ab dem 1.1.2000"). Fuer WSV-Pegel (Over, Zollenspieker) stehen dort
minuetliche Rohdaten seit 2000 bereit. Der HPA-Pegel Hamburg St. Pauli ist NICHT
im Archiv; fuer Zeitraeume innerhalb der letzten ~31 Tage wird er ersatzweise
ueber die PEGELONLINE-REST-API gezogen (``--no-rest-fallback`` schaltet das ab).

Fuer das laufende monatliche Update NICHT dieses Skript nehmen, sondern
``update_history.py`` (inkrementell, nur die juengsten Jahres-Partitionen).

Beispiele:

    # Kleiner Testzeitraum -> out/history/ (year=YYYY/...)
    python build_history.py --start 2000-01-01 --end 2000-01-08 \
        --stations over zollenspieker

    # Voller Backfill + Upload zu Hugging Face (spiegelt das Repo komplett)
    HF_TOKEN=... python build_history.py --start 2000-01-01 --end 2026-07-01 \
        --stations over zollenspieker --hf-repo
"""

from __future__ import annotations

import argparse

from wasserstand_overwerder import history
from wasserstand_overwerder.config import PEGELONLINE_HF_REPO, PEGELONLINE_STATION_UUIDS

ALL_STATIONS = list(PEGELONLINE_STATION_UUIDS)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--start", required=True, help="Startdatum/-zeit (gesetzliche Zeit, inkl.)"
    )
    ap.add_argument(
        "--end", required=True, help="Enddatum/-zeit (gesetzliche Zeit, exkl.)"
    )
    ap.add_argument(
        "--stations",
        nargs="+",
        default=ALL_STATIONS,
        choices=ALL_STATIONS,
        help=f"Stationen (Default: {' '.join(ALL_STATIONS)})",
    )
    ap.add_argument("--out", default="out/history", help="Ziel-Verzeichnis (Parquet)")
    ap.add_argument(
        "--no-rest-fallback",
        dest="rest_fallback",
        action="store_false",
        help="Pegel ohne Archiv (St. Pauli) NICHT ueber die REST-API ergaenzen",
    )
    ap.add_argument(
        "--hf-repo",
        nargs="?",
        const=PEGELONLINE_HF_REPO,
        default=None,
        metavar="ORG/NAME",
        help=(
            "nach dem Schreiben zu Hugging Face SPIEGELN (voller Ersatz); "
            f"ohne Wert -> {PEGELONLINE_HF_REPO}; braucht HF_TOKEN"
        ),
    )
    args = ap.parse_args()

    df = history.fetch_station_frames(
        args.stations, args.start, args.end, rest_fallback=args.rest_fallback
    )
    if df.empty:
        raise SystemExit("Keine Daten geladen.")

    out = history.write_parquet(df, args.out)
    years = sorted(df["year"].unique())
    print(
        f"\n-> {len(df)} Zeilen nach {out}/ geschrieben "
        f"(year-Partitionen: {', '.join(map(str, years))})"
    )

    if args.hf_repo:  # nicht gesetzt -> None; ohne Wert -> PEGELONLINE_HF_REPO
        from wasserstand_overwerder import hfhub

        print(f"Spiegle nach Hugging Face: {args.hf_repo} ...", flush=True)
        # replace_years=None -> voller Spiegel (alte Fragmente werden ersetzt)
        url = hfhub.upload_dataset(
            out,
            repo_id=args.hf_repo,
            stations=list(args.stations),
            commit_message=f"Voller Backfill {years[0]}..{years[-1]}",
        )
        print(f"-> {url}")


if __name__ == "__main__":
    main()
