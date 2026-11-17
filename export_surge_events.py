"""Over-Kurven der Top-Sturmfluten -> web/public/surge_events.json (eingecheckt).

Laedt nur die noetigen Jahre aus dem Hugging-Face-Archiv (Extra ``hf``) oder
aus einer lokalen Parquet-Datei (``--data``, Spalten time/station/w_cm_pnp).
Die Web-Karte zeigt damit den Scheitel eines Ereignisses, wenn man im Chart
auf dessen Top-10-Linie klickt.

    uv sync --extra hf
    uv run python export_surge_events.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from wasserstand_overwerder import surge_events
from wasserstand_overwerder.config import (
    PEGELONLINE_HF_REPO,
    PLAUSIBLE_CM_PNP,
    STURMFLUT_SCHEITEL_ZEIT,
)


def load_over(years: set[int], data: str | None) -> pd.Series:
    if data:
        df = pd.read_parquet(data)
        df = df[df["station"] == "over"]
    else:
        import pyarrow.dataset as ds
        from huggingface_hub import HfFileSystem

        fs = HfFileSystem()
        files = [
            f
            for y in sorted(years)
            for f in fs.glob(f"datasets/{PEGELONLINE_HF_REPO}/year={y}/*.parquet")
        ]
        tbl = ds.dataset(files, filesystem=fs, format="parquet").to_table(
            columns=["time", "w_cm_pnp"], filter=ds.field("station") == "over"
        )
        df = tbl.to_pandas()
    s = pd.Series(df["w_cm_pnp"].to_numpy(), index=pd.DatetimeIndex(df["time"]))
    if s.index.tz is None:
        s.index = s.index.tz_localize("UTC")
    lo, hi = PLAUSIBLE_CM_PNP
    s = s.sort_index()
    return s[(s >= lo) & (s <= hi) & ~s.index.duplicated()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="web/public/surge_events.json")
    ap.add_argument("--data", help="lokale Parquet-Datei statt Hugging Face")
    args = ap.parse_args()

    # Jahr des Scheitels und ggf. Vorjahr (Ausschnitt reicht 3 Tage zurueck).
    years = set()
    for local in STURMFLUT_SCHEITEL_ZEIT.values():
        t = surge_events.peak_utc(local)
        years |= {t.year, (t - pd.Timedelta(days=4)).year}
    print(f"Lade Over fuer {sorted(years)} ...")
    s = load_over(years, args.data)
    events = surge_events.build_events(s)
    for e in events:
        diff = e["peak_cm"] - e["cm"]
        print(
            f"  #{e['rank']} {e['label']}: Scheitel {e['peak']} {e['peak_cm']} cm "
            f"(Liste {e['cm']:.0f}, {diff:+.0f}), {len(e['series'])} Punkte"
        )
    out = Path(args.out)
    out.write_text(json.dumps({"events": events}, separators=(",", ":")))
    print(f"-> {out} ({out.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
