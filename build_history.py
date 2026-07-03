#!/usr/bin/env python3
"""Baut ein jaehrlich partitioniertes Parquet-Archiv minuetlicher Wasserstaende.

Quelle: PEGELONLINE-Langzeitarchiv ("Download langfristiger Wasserstaende
(Rohdaten) ab dem 1.1.2000"). Fuer WSV-Pegel (Over, Zollenspieker) stehen dort
minuetliche Rohdaten seit 2000 bereit. Der HPA-Pegel Hamburg St. Pauli ist NICHT
im Archiv; fuer Zeitraeume innerhalb der letzten ~31 Tage wird er ersatzweise
ueber die PEGELONLINE-REST-API gezogen (``--rest-fallback``, Default an).

Beispiele:

    # Kleiner Testzeitraum, alle Stationen -> out/history/ (year=YYYY/...)
    python build_history.py --start 2000-01-01 --end 2000-01-08 \
        --stations over zollenspieker

    # Gesamtes Archiv eines Pegels
    python build_history.py --start 2000-01-01 --end 2026-07-01 --stations over

Die Ausgabe ist ein Hive-partitioniertes Parquet-Dataset (``year=YYYY/``), das
sich taeglich/monatlich per erneutem Aufruf mit spaeterem Zeitraum erweitern
laesst.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from wasserstand_overwerder import history, pegelonline
from wasserstand_overwerder.config import PEGELONLINE_STATION_UUIDS
from wasserstand_overwerder.hfhub import DEFAULT_HF_REPO

ALL_STATIONS = list(PEGELONLINE_STATION_UUIDS)


def _fetch_rest_fallback(key: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Ersatz ueber die REST-API (nur letzte ~31 Tage) fuer Pegel ohne Archiv."""
    s = pegelonline.observations(key, start=start.strftime("%Y-%m-%dT%H:%M:%S%z"))
    return s[(s.index >= start) & (s.index < end)]


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
        const=None,
        default=argparse.SUPPRESS,
        metavar="ORG/NAME",
        help=(
            "nach dem Schreiben zu Hugging Face hochladen "
            f"(Default-Repo: {DEFAULT_HF_REPO}); braucht HF_TOKEN"
        ),
    )
    args = ap.parse_args()
    hf_repo = getattr(args, "hf_repo", False)  # False = Flag nicht gesetzt

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    start_utc = (
        start.tz_localize(history.PEGELONLINE_HISTORY_TZ)
        if start.tzinfo is None
        else start
    ).tz_convert("UTC")
    end_utc = (
        end.tz_localize(history.PEGELONLINE_HISTORY_TZ) if end.tzinfo is None else end
    ).tz_convert("UTC")

    frames: list[pd.DataFrame] = []
    for key in args.stations:
        print(f"[{key}] lade {args.start} .. {args.end} ...", flush=True)
        try:
            series = history.fetch_history(key, args.start, args.end)
            src = "Archiv"
        except history.ArchiveNotAvailable:
            if not args.rest_fallback:
                print(f"  ! {key}: kein Langzeitarchiv, uebersprungen")
                continue
            print(f"  i {key}: kein Langzeitarchiv -> REST-Fallback (max. 31 Tage)")
            try:
                series = _fetch_rest_fallback(key, start_utc, end_utc)
                src = "REST"
            except Exception as exc:  # noqa: BLE001 - Netzfehler nur berichten
                print(f"  ! {key}: REST-Fallback fehlgeschlagen: {exc}")
                continue
        if series.empty:
            print(f"  ! {key}: keine Werte im Zeitraum")
            continue
        print(
            f"  {key}: {len(series)} Werte ({src}), "
            f"{series.index.min()} .. {series.index.max()}"
        )
        frames.append(history.series_to_frame(series, key))

    if not frames:
        print("Keine Daten geladen.", file=sys.stderr)
        raise SystemExit(1)

    df = pd.concat(frames, ignore_index=True)
    out = history.write_parquet(df, args.out)
    years = sorted(df["year"].unique())
    print(
        f"\n-> {len(df)} Zeilen nach {out}/ geschrieben "
        f"(year-Partitionen: {', '.join(map(str, years))})"
    )

    if hf_repo is not False:  # --hf-repo gesetzt (ggf. ohne Wert -> Default)
        from wasserstand_overwerder import hfhub

        repo_id = hf_repo or DEFAULT_HF_REPO
        print(f"Lade nach Hugging Face: {repo_id} ...", flush=True)
        url = hfhub.upload_dataset(out, repo_id=repo_id, stations=list(args.stations))
        print(f"-> {url}")


if __name__ == "__main__":
    main()
