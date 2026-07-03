"""PEGELONLINE-Langzeitarchiv: minuetliche Rohdaten (W, cm ueber PNP) seit 2000.

Das oeffentliche Formular "Download langfristiger Wasserstaende (Rohdaten) ab
dem 1.1.2000" auf den Stammdatenseiten von PEGELONLINE laeuft ueber zwei
Schritte:

1. POST an ``/gast/historische-zeitreihen/prepare-download`` (uuid, parameter,
   start, end, format) -> 303-Redirect auf eine generierte Download-URL.
2. GET dieser URL liefert ein ZIP mit ``*.csv`` (Kopf ``timestamp;value``),
   ``zeitreiheninformation.txt`` und ``nutzungsbedingungen.txt``.

Die Zeitstempel stehen in gesetzlicher Zeit (MEZ/MESZ, mit Sommerzeit); wir
lokalisieren sie nach ``Europe/Berlin`` und geben tz-aware UTC zurueck. Werte
sind cm ueber PNP.

Nur WSV-Pegel haben dieses Archiv. HPA-Pegel wie HAMBURG ST. PAULI liefern nur
die rollierenden 31 Tage der REST-API (siehe :mod:`pegelonline`).
"""

from __future__ import annotations

import io
import uuid as _uuid
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import requests

from .config import (
    HTTP_TIMEOUT,
    PEGELONLINE_HISTORY_PARAMETER,
    PEGELONLINE_HISTORY_TZ,
    PEGELONLINE_STATION_UUIDS,
    PEGELONLINE_WEB_BASE,
    USER_AGENT,
)

_PREPARE_URL = f"{PEGELONLINE_WEB_BASE}/historische-zeitreihen/prepare-download"
_ERROR_MARKER = "errorpages"


class ArchiveNotAvailable(RuntimeError):
    """Fuer diese Station gibt es kein Langzeitarchiv (z. B. HPA-Pegel)."""


def _to_berlin_iso(value: str | pd.Timestamp) -> str:
    """Zeitangabe nach Europe/Berlin in ISO-8601 mit Offset (z. B. +01:00).

    Nackte Zeitstempel/Datumsstrings werden als gesetzliche Zeit interpretiert;
    tz-aware Angaben werden nach Europe/Berlin konvertiert.
    """
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(PEGELONLINE_HISTORY_TZ)
    else:
        ts = ts.tz_convert(PEGELONLINE_HISTORY_TZ)
    return ts.strftime("%Y-%m-%dT%H:%M:%S%z")


def _session(session: requests.Session | None) -> requests.Session:
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", USER_AGENT)
    return s


def prepare_download_url(
    uuid: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    session: requests.Session | None = None,
) -> str:
    """Schritt 1: Download vorbereiten, absolute Download-URL zurueckgeben."""
    s = _session(session)
    r = s.post(
        _PREPARE_URL,
        data={
            "uuid": uuid,
            "parameter": PEGELONLINE_HISTORY_PARAMETER,
            "start": _to_berlin_iso(start),
            "end": _to_berlin_iso(end),
            "format": "csv",
        },
        timeout=HTTP_TIMEOUT,
        allow_redirects=False,
    )
    location = r.headers.get("Location", "")
    if r.status_code not in (301, 302, 303) or not location:
        raise RuntimeError(
            f"prepare-download unerwartete Antwort (HTTP {r.status_code}): {location!r}"
        )
    if _ERROR_MARKER in location:
        raise ArchiveNotAvailable(
            f"Kein Langzeitarchiv fuer uuid={uuid} (Server-Fehlerseite: {location})"
        )
    if location.startswith("http"):
        return location
    return f"{PEGELONLINE_WEB_BASE.rsplit('/gast', 1)[0]}{location}"


def _parse_csv_bytes(raw: bytes) -> pd.Series:
    """CSV-Bytes (timestamp;value, gesetzliche Zeit) -> Serie tz-aware UTC."""
    df = pd.read_csv(
        io.BytesIO(raw), sep=";", header=0, names=["timestamp", "value"], dtype=str
    )
    naive = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M")
    idx = (
        naive.dt.tz_localize(
            PEGELONLINE_HISTORY_TZ, ambiguous="infer", nonexistent="shift_forward"
        )
        .dt.tz_convert("UTC")
        .to_numpy()
    )
    values = pd.to_numeric(df["value"], errors="coerce")
    s = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(idx)).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.dropna()


def _extract_csv(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                return zf.read(name)
    raise RuntimeError("ZIP enthaelt keine CSV-Datei")


def fetch_history(
    key: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    session: requests.Session | None = None,
) -> pd.Series:
    """Minuetliche Rohdaten (cm ueber PNP) fuer ``key`` im Zeitraum [start, end).

    ``key`` ist ein Schluessel aus ``PEGELONLINE_STATION_UUIDS`` (z. B. "over",
    "zollenspieker"). Rueckgabe: Serie mit tz-aware UTC-Index, Name = ``key``.

    Wirft :class:`ArchiveNotAvailable`, wenn die Station kein Langzeitarchiv hat.
    """
    try:
        uuid = PEGELONLINE_STATION_UUIDS[key]
    except KeyError as exc:
        raise KeyError(f"Unbekannte Station {key!r}") from exc
    s = _session(session)
    url = prepare_download_url(uuid, start, end, session=s)
    r = s.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    series = _parse_csv_bytes(_extract_csv(r.content))
    series.name = key
    return series


# --- Parquet: tidy long-format, jaehrlich partitioniert -------------------

#: Spalten des Parquet-Datensatzes.
#: ``time`` tz-aware UTC, ``station`` Schluessel, ``w_cm_pnp`` Wasserstand,
#: ``year`` UTC-Jahr als Partitionsspalte.
PARQUET_COLUMNS = ("time", "station", "w_cm_pnp", "year")

#: Standard-Kompression: zstd (rund halb so gross wie snappy bei gleicher
#: Lesbarkeit; ~110 statt ~250 MB fuers Gesamtarchiv Over+Zollenspieker).
PARQUET_COMPRESSION = "zstd"


def series_to_frame(series: pd.Series, key: str | None = None) -> pd.DataFrame:
    """Serie (UTC-Index, cm ueber PNP) -> tidy DataFrame mit ``year``-Spalte."""
    station = key or series.name
    idx = pd.DatetimeIndex(series.index)
    return pd.DataFrame(
        {
            "time": idx,
            "station": pd.array([station] * len(series), dtype="string"),
            "w_cm_pnp": pd.to_numeric(series.to_numpy(), errors="coerce"),
            "year": idx.year.astype("int32"),
        }
    )


def write_parquet(
    frame: pd.DataFrame,
    out_dir: str | Path,
    compression: str = PARQUET_COMPRESSION,
) -> Path:
    """Tidy-DataFrame als jaehrlich partitioniertes Parquet-Dataset schreiben.

    Partitionierung ueber ``year`` (Verzeichnisse ``year=YYYY/``). Bestehende
    Partitionen bleiben erhalten; jeder Aufruf legt eindeutig benannte Fragmente
    an (``existing_data_behavior="overwrite_or_ignore"``), sodass taeglich oder
    monatlich angehaengt werden kann. Kompression per Default ``zstd``.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame[list(PARQUET_COLUMNS)], preserve_index=False)
    file_options = ds.ParquetFileFormat().make_write_options(compression=compression)
    ds.write_dataset(
        table,
        base_dir=str(out),
        format="parquet",
        file_options=file_options,
        partitioning=["year"],
        partitioning_flavor="hive",
        existing_data_behavior="overwrite_or_ignore",
        basename_template=f"part-{_uuid.uuid4().hex}-{{i}}.parquet",
    )
    return out


def read_parquet(out_dir: str | Path) -> pd.DataFrame:
    """Partitioniertes Parquet-Dataset einlesen (bequem fuer Tests/Analyse)."""
    dataset = ds.dataset(str(out_dir), format="parquet", partitioning="hive")
    df = dataset.to_table().to_pandas()
    if "time" in df:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    return df
