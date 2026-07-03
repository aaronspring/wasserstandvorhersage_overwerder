"""PEGELONLINE REST-API v2: Beobachtungen (W, cm ueber PNP) der letzten <=31 Tage."""

from urllib.parse import quote

import pandas as pd
import requests

from .config import HTTP_TIMEOUT, PEGELONLINE_BASE, PEGELONLINE_STATIONS, USER_AGENT


def _get(url: str, **params) -> requests.Response:
    r = requests.get(
        url, params=params, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}
    )
    r.raise_for_status()
    return r


def station_info(key: str) -> dict:
    """Stations-Metadaten inkl. gaugeZero (PNP in m ue. NHN)."""
    name = PEGELONLINE_STATIONS[key]
    url = f"{PEGELONLINE_BASE}/stations/{quote(name)}.json"
    r = _get(url, includeTimeseries="true", includeCharacteristicValues="true")
    return r.json()


def characteristic_values(key: str) -> dict[str, float]:
    """Kennwerte (z. B. MHW, MNW) der W-Zeitreihe in cm ueber PNP.

    Rueckgabe: {shortname: wert_cm}, z. B. {"MHW": 744.0, "MNW": 430.0}.
    Fehlt der Kennwerte-Block, wird ein leeres Dict zurueckgegeben.
    """
    info = station_info(key)
    for ts in info.get("timeseries", []):
        if ts.get("shortname") != "W":
            continue
        out: dict[str, float] = {}
        for cv in ts.get("characteristicValues") or []:
            name, value = cv.get("shortname"), cv.get("value")
            if name and value is not None:
                out[str(name)] = float(value)
        return out
    return {}


def gauge_zero_m_nhn(key: str) -> float | None:
    """PNP in m ueber NHN (fuer Tideelbe-Pegel typischerweise -5.00)."""
    info = station_info(key)
    for ts in info.get("timeseries", []):
        if ts.get("shortname") == "W":
            gz = ts.get("gaugeZero") or {}
            if gz.get("value") is not None:
                return float(gz["value"])
    return None


def observations(key: str, start: str = "P10D") -> pd.Series:
    """Wasserstand W in cm ueber PNP als Serie mit UTC-Zeitindex.

    start: ISO-8601-Dauer (z.B. "P30D") oder Zeitstempel, wie von der API akzeptiert.
    """
    name = PEGELONLINE_STATIONS[key]
    url = f"{PEGELONLINE_BASE}/stations/{quote(name)}/W/measurements.json"
    data = _get(url, start=start).json()
    if not data:
        raise RuntimeError(f"PEGELONLINE lieferte keine Messwerte fuer {name}")
    ts = pd.to_datetime([d["timestamp"] for d in data], utc=True)
    values = [d["value"] for d in data]
    s = pd.Series(values, index=ts, name=key).sort_index()
    return s[~s.index.duplicated(keep="last")]
