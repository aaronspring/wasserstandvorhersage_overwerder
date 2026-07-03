"""Netzfreie Tests fuer das Langzeitarchiv (Parsing, Parquet, Fehlerpfade)."""

import io
import os
import sys
import zipfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import history

# Minuetliche Roh-CSV wie im PEGELONLINE-Archiv (Kopf timestamp;value,
# Zeitstempel in gesetzlicher Zeit MEZ/MESZ, Werte cm ueber PNP).
_WINTER_CSV = (
    b"timestamp;value\n"
    b"2000-01-01 01:00;682\n"
    b"2000-01-01 01:01;681\n"
    b"2000-01-01 01:02;680\n"
)

# Sommerzeit: 12:00 MESZ (+02) == 10:00 UTC.
_SUMMER_CSV = b"timestamp;value\n2020-07-01 12:00;550\n2020-07-01 12:01;551\n"


def test_parse_winter_csv_to_utc():
    s = history._parse_csv_bytes(_WINTER_CSV)
    assert s.index.tz is not None and str(s.index.tz) == "UTC"
    # 01:00 MEZ (+01) -> 00:00 UTC
    assert s.index[0] == pd.Timestamp("2000-01-01 00:00", tz="UTC")
    assert list(s.values) == [682, 681, 680]
    assert s.index.is_monotonic_increasing and s.index.is_unique


def test_parse_summer_csv_dst_offset():
    s = history._parse_csv_bytes(_SUMMER_CSV)
    # 12:00 MESZ (+02) -> 10:00 UTC
    assert s.index[0] == pd.Timestamp("2020-07-01 10:00", tz="UTC")


def test_series_to_frame_columns_and_year():
    s = history._parse_csv_bytes(_WINTER_CSV)
    df = history.series_to_frame(s, "over")
    assert list(df.columns) == list(history.PARQUET_COLUMNS)
    assert (df["station"] == "over").all()
    assert (df["year"] == 2000).all()
    assert df["time"].dt.tz is not None


def test_parquet_roundtrip_partitioned_by_year(tmp_path):
    # Zwei Jahre + zwei Stationen -> zwei year-Partitionen erwartet.
    idx1 = pd.date_range("2000-01-01", periods=3, freq="min", tz="UTC")
    idx2 = pd.date_range("2001-01-01", periods=2, freq="min", tz="UTC")
    df = pd.concat(
        [
            history.series_to_frame(pd.Series([1, 2, 3], index=idx1), "over"),
            history.series_to_frame(pd.Series([4, 5], index=idx2), "zollenspieker"),
        ],
        ignore_index=True,
    )
    out = history.write_parquet(df, tmp_path / "hist")
    part_dirs = sorted(p.name for p in out.iterdir() if p.is_dir())
    assert part_dirs == ["year=2000", "year=2001"]

    back = history.read_parquet(out)
    assert len(back) == 5
    assert set(back["station"]) == {"over", "zollenspieker"}
    assert set(back["year"]) == {2000, 2001}
    assert str(back["time"].dt.tz) == "UTC"


def test_write_parquet_append_keeps_existing(tmp_path):
    idx1 = pd.date_range("2000-01-01", periods=2, freq="min", tz="UTC")
    idx2 = pd.date_range("2000-01-02", periods=3, freq="min", tz="UTC")
    history.write_parquet(
        history.series_to_frame(pd.Series([1, 2], index=idx1), "over"), tmp_path / "h"
    )
    history.write_parquet(
        history.series_to_frame(pd.Series([3, 4, 5], index=idx2), "over"),
        tmp_path / "h",
    )
    back = history.read_parquet(tmp_path / "h")
    # Zweiter Aufruf haengt an, statt die erste Partition zu ueberschreiben.
    assert len(back) == 5


def test_extract_csv_picks_csv_member():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nutzungsbedingungen.txt", "...")
        zf.writestr("zeitreiheninformation.txt", "station_name=OVER")
        zf.writestr("pegelonline-over-W-20000101-20000102.csv", _WINTER_CSV)
    assert history._extract_csv(buf.getvalue()) == _WINTER_CSV


class _FakeResp:
    def __init__(self, status_code, location):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp
        self.headers = {}

    def post(self, *a, **k):
        return self._resp


def test_prepare_download_url_raises_on_error_redirect():
    sess = _FakeSession(_FakeResp(303, "https://host/errorpages/errorException"))
    try:
        history.prepare_download_url("uuid", "2000-01-01", "2000-01-02", session=sess)
    except history.ArchiveNotAvailable:
        return
    raise AssertionError("Fehler-Redirect sollte ArchiveNotAvailable ausloesen")


def test_prepare_download_url_returns_absolute():
    sess = _FakeSession(_FakeResp(303, "https://host/gast/.../download?filename=x.zip"))
    url = history.prepare_download_url("u", "2000-01-01", "2000-01-02", session=sess)
    assert url == "https://host/gast/.../download?filename=x.zip"


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            if "tmp_path" in fn.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"ok  {name}")
    print("Alle Tests bestanden.")
