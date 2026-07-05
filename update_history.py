#!/usr/bin/env python3
"""Inkrementelles Monatsupdate des Pegel-Archivs auf Hugging Face.

Baut nur die juengsten Jahres-Partitionen neu (laufendes Jahr + ``--years-back``
Vorjahre) und ersetzt genau diese im HF-Dataset. Aeltere Jahre (2000..) bleiben
unberuehrt und werden weder neu geladen noch hochgeladen. Damit bleibt das
Update guenstig (~wenige MB, wenige Minuten) und idempotent (keine Duplikate,
sauber ueber Jahreswechsel dank Vorjahr-Refresh).

Voraussetzung: einmaliger voller Backfill via ``build_history.py --hf-repo``.

    HF_TOKEN=... python update_history.py            # Default-Repo, 1 Vorjahr
    HF_TOKEN=... python update_history.py --years-back 0   # nur laufendes Jahr
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

from wasserstand_overwerder import hfhub, history
from wasserstand_overwerder.config import (
    PEGELONLINE_ARCHIVE_STATIONS,
    PEGELONLINE_HF_REPO,
    PEGELONLINE_STATION_UUIDS,
)

DEFAULT_STATIONS = list(PEGELONLINE_ARCHIVE_STATIONS)  # nur Pegel mit Langzeitarchiv


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--hf-repo", default=PEGELONLINE_HF_REPO, metavar="ORG/NAME", help="Ziel-Repo"
    )
    ap.add_argument(
        "--years-back",
        type=int,
        default=1,
        help="zusaetzlich zum laufenden Jahr N Vorjahre neu bauen (Default 1)",
    )
    ap.add_argument(
        "--stations",
        nargs="+",
        default=DEFAULT_STATIONS,
        choices=list(PEGELONLINE_STATION_UUIDS),
        help=f"Stationen (Default: {' '.join(DEFAULT_STATIONS)})",
    )
    ap.add_argument("--out", default="out/history_update", help="lokales Arbeitsverz.")
    ap.add_argument(
        "--no-upload",
        dest="upload",
        action="store_false",
        help="nur lokal bauen, nicht zu Hugging Face hochladen",
    )
    args = ap.parse_args()

    today = dt.datetime.now(dt.UTC).date()
    first_year = today.year - max(args.years_back, 0)
    years = list(range(first_year, today.year + 1))
    start = f"{first_year}-01-01"
    end = today.isoformat()
    print(f"Inkrementelles Update: Jahre {years} ({start} .. {end})")

    df = history.fetch_station_frames(args.stations, start, end, rest_fallback=False)
    if df.empty:
        raise SystemExit("Keine Daten geladen.")

    out = history.write_parquet(df, args.out)
    built_years = sorted(int(y) for y in df["year"].unique())
    print(f"-> {len(df)} Zeilen, Partitionen {built_years} nach {out}/")

    if args.upload:
        print(f"Ersetze auf Hugging Face ({args.hf_repo}) nur: {built_years}")
        url = hfhub.upload_dataset(
            out,
            repo_id=args.hf_repo,
            stations=list(args.stations),
            replace_years=built_years,
            commit_message=f"Inkrementelles Update {pd.Timestamp(end).date()} "
            f"(Jahre {built_years})",
        )
        print(f"-> {url}")


if __name__ == "__main__":
    main()
