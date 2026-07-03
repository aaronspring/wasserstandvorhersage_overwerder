"""Client fuer die BSH-Wasserstandsvorhersage (OGC API Features / ldproxy).

Der Dienst https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast ist
offen (CC BY 4.0), aber die Collection- und Feldnamen sind nicht stabil
dokumentiert. Dieser Client entdeckt die Struktur zur Laufzeit:

1. /collections listet die Feature-Collections.
2. Kandidaten-Collections (Namen mit forecast/vorhersage/kurve/...) werden
   angelesen; Zeit-, Wert- und Stationsfelder werden heuristisch erkannt.
   Enthaelt ein Feature mehrere eingebettete Zeitreihen (BSH: dichte `curve`
   und grobe `high_water_low_water`), wird die dichteste Kurve bevorzugt;
   pro Zeitschritt gewinnt das Vorhersagefeld (automated_curve_forecast) vor
   Messung vor astronomischer Vorausberechnung. Werte duerfen Strings sein.
3. Features der gewuenschten Station werden (serverseitig gefiltert, sonst
   seitenweise) geladen und zu einer Zeitreihe zusammengesetzt.

Mit `python forecast.py --explore` laesst sich die API-Struktur ausgeben,
falls die Heuristik angepasst werden muss (config.py).
"""

from __future__ import annotations

import re

import pandas as pd
import requests

from .config import (
    BSH_BASE,
    BSH_DATUM_OFFSET_CM,
    BSH_STATION_PATTERNS,
    HTTP_TIMEOUT,
    PLAUSIBLE_CM_PNP,
    USER_AGENT,
)

_FORECAST_HINTS = ("forecast", "vorhersage", "curve", "kurve", "prediction",
                   "timeseries", "zeitreihe", "wlf", "data")
_TIME_KEY_HINTS = ("time", "date", "zeit", "stamp")
_VALUE_KEY_HINTS = ("value", "wert", "level", "height", "wasserstand",
                    "forecast", "vorhersage")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


class BSHClient:
    def __init__(self, base: str = BSH_BASE):
        self.base = base.rstrip("/")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _get_json(self, url: str, **params) -> dict:
        params.setdefault("f", "json")
        r = self.session.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()

    # -- Discovery -----------------------------------------------------------

    def collections(self) -> list[dict]:
        return self._get_json(f"{self.base}/collections").get("collections", [])

    def _items_url(self, collection_id: str) -> str:
        return f"{self.base}/collections/{collection_id}/items"

    def sample_features(self, collection_id: str, limit: int = 3) -> list[dict]:
        data = self._get_json(self._items_url(collection_id), limit=limit)
        return data.get("features", [])

    def iter_features(self, collection_id: str, max_pages: int = 50, **params):
        """Alle Features einer Collection, folgt rel=next-Links."""
        url, first = self._items_url(collection_id), True
        for _ in range(max_pages):
            data = self._get_json(url, **(params if first else {"f": "json"}))
            yield from data.get("features", [])
            nxt = [l for l in data.get("links", []) if l.get("rel") == "next"]
            if not nxt:
                return
            url, first = nxt[0]["href"], False

    def explore(self) -> None:
        """API-Struktur ausgeben (Collections + je ein Beispiel-Feature)."""
        import json
        for c in self.collections():
            cid = c.get("id", "?")
            print(f"\n=== Collection: {cid}  ({c.get('title', '')})")
            try:
                feats = self.sample_features(cid, limit=1)
            except requests.RequestException as e:
                print(f"    Fehler beim Lesen: {e}")
                continue
            for f in feats:
                print(json.dumps(f.get("properties", {}), indent=2,
                                 ensure_ascii=False, default=str)[:2000])

    # -- Heuristiken ---------------------------------------------------------

    @staticmethod
    def _as_float(v) -> float | None:
        """int/float oder numerischer String -> float, sonst None.

        Die BSH-Kurve liefert Werte als Strings ("478"); Bool ist kein Wert.
        """
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.strip().replace(",", "."))
            except ValueError:
                return None
        return None

    @staticmethod
    def _find_key(props: dict, hints: tuple[str, ...],
                  pred=lambda v: True) -> str | None:
        for k, v in props.items():
            if any(h in k.lower() for h in hints) and v is not None and pred(v):
                return k
        return None

    @staticmethod
    def _is_time(v) -> bool:
        try:
            return bool(pd.notna(pd.to_datetime(v, utc=True)))
        except (ValueError, TypeError):
            return False

    @classmethod
    def _time_key(cls, props: dict) -> str | None:
        return cls._find_key(props, _TIME_KEY_HINTS, cls._is_time)

    @classmethod
    def _time_key_across(cls, items: list[dict]) -> str | None:
        """Zeitfeld ueber eine Liste von Eintraegen (Feld kann fehlen).

        Waehlt das am haeufigsten parsebare Feld mit Zeit-Namenshinweis,
        sonst das erste ueberhaupt als Zeit parsebare Feld.
        """
        counts: dict[str, int] = {}
        for it in items:
            for k, v in it.items():
                if any(h in k.lower() for h in _TIME_KEY_HINTS) and cls._is_time(v):
                    counts[k] = counts.get(k, 0) + 1
        if counts:
            return max(counts, key=counts.get)
        for k, v in items[0].items():
            if cls._is_time(v):
                return k
        return None

    @staticmethod
    def _value_rank(key: str) -> int:
        """Praeferenz fuer Wertfelder: Vorhersage > Messung > sonstige Numerik.

        In der BSH-Kurve: automated_curve_forecast (Rang 0, Zukunft) vor
        measurement (Rang 2, Vergangenheit) vor tidal_prediction (Rang 3,
        astronomisch).
        """
        k = key.lower()
        if any(h in k for h in ("forecast", "vorhersage")):
            return 0
        if any(h in k for h in _VALUE_KEY_HINTS):
            return 1
        if any(h in k for h in ("measure", "mess", "observ", "beob")):
            return 2
        return 3

    @classmethod
    def _value_key(cls, props: dict) -> str | None:
        key = cls._find_key(props, _VALUE_KEY_HINTS,
                            lambda v: cls._as_float(v) is not None)
        if key:
            return key
        numeric = [k for k, v in props.items() if cls._as_float(v) is not None]
        return numeric[0] if len(numeric) == 1 else None

    @staticmethod
    def _matches_station(props: dict, patterns: tuple[str, ...]) -> bool:
        for v in props.values():
            if isinstance(v, str) and any(p in _norm(v) for p in patterns):
                return True
        return False

    def _forecast_collections(self) -> list[str]:
        cols = self.collections()
        scored = []
        for c in cols:
            text = _norm(c.get("id", "")) + " " + _norm(c.get("title", ""))
            score = sum(h in text for h in _FORECAST_HINTS)
            scored.append((score, c.get("id")))
        scored.sort(reverse=True)
        return [cid for score, cid in scored if cid] or [c.get("id") for c in cols]

    # -- Vorhersage ----------------------------------------------------------

    def forecast(self, station_key: str) -> pd.Series:
        """Kurvenvorhersage einer Station als Serie (cm ueber PNP, UTC-Index)."""
        patterns = BSH_STATION_PATTERNS[station_key]
        errors: list[str] = []
        for cid in self._forecast_collections():
            try:
                series = self._forecast_from_collection(cid, patterns)
            except requests.RequestException as e:
                errors.append(f"{cid}: {e}")
                continue
            if series is not None and len(series) >= 8:
                series.name = station_key
                return self._to_cm_pnp(series, station_key)
        raise RuntimeError(
            f"Keine BSH-Vorhersage fuer '{station_key}' gefunden. "
            f"Bitte `python forecast.py --explore` ausfuehren und "
            f"config.py anpassen. Fehler: {errors}"
        )

    def _forecast_from_collection(self, cid: str,
                                  patterns: tuple[str, ...]) -> pd.Series | None:
        samples = self.sample_features(cid, limit=5)
        if not samples:
            return None
        props = samples[0].get("properties", {})

        # Variante A: ein Feature pro Station mit eingebetteter Zeitreihe (Liste).
        # Enthaelt ein Feature mehrere Listen (BSH: dichte `curve` UND grobe
        # `high_water_low_water`), die dichte Kurve bevorzugen: erst
        # Namenshinweis (curve/kurve/series), dann groesste Liste.
        list_keys = [k for k, v in props.items()
                     if isinstance(v, list) and v and isinstance(v[0], dict)
                     and self._time_key_across(v)]
        if list_keys:
            key = max(list_keys, key=lambda k: (
                any(h in k.lower() for h in ("curve", "kurve", "series")),
                len(props[k])))
            try:  # grosse Seite anfordern (Features sind schwer)
                feats = list(self.iter_features(cid, limit=10000))
            except requests.RequestException:
                feats = list(self.iter_features(cid))
            for f in feats:
                p = f.get("properties", {})
                if self._matches_station(p, patterns):
                    series = self._parse_embedded(p.get(key, []))
                    if series is not None:
                        return series
            return None

        # Variante B: ein Feature pro Zeitschritt
        tkey, vkey = self._time_key(props), self._value_key(props)
        if not (tkey and vkey):
            return None
        records = []
        try:  # grosse Seiten anfordern, um Paginierung zu minimieren
            feats = list(self.iter_features(cid, limit=10000))
        except requests.RequestException:
            feats = list(self.iter_features(cid))
        for f in feats:
            p = f.get("properties", {})
            if not self._matches_station(p, patterns):
                continue
            try:
                t = pd.to_datetime(p[tkey], utc=True)
            except (ValueError, TypeError, KeyError):
                continue
            v = self._as_float(p.get(vkey))
            if v is not None:
                records.append((t, v))
        if not records:
            return None
        s = pd.Series(dict(records)).sort_index()
        return s[~s.index.duplicated(keep="last")]

    def _parse_embedded(self, items: list[dict]) -> pd.Series | None:
        """Eingebettete Zeitreihe (Liste von Dicts) -> Serie.

        Das Zeit- und das Wertfeld koennen je Eintrag unterschiedlich belegt
        sein (BSH-Kurve: Vergangenheit hat `measurement`, Zukunft
        `automated_curve_forecast`). Pro Eintrag wird das hoechstrangige
        vorhandene Wertfeld gewaehlt (_value_rank) und aus String/Zahl
        gelesen.
        """
        if not items:
            return None
        tkey = self._time_key_across(items)
        if tkey is None:
            return None
        cand = {k for it in items for k, v in it.items()
                if k != tkey and self._as_float(v) is not None}
        if not cand:
            return None
        order = sorted(cand, key=lambda k: (self._value_rank(k), k))
        idx, vals = [], []
        for it in items:
            t = it.get(tkey)
            val = next((self._as_float(it[k]) for k in order
                        if self._as_float(it.get(k)) is not None), None)
            if t is None or val is None:
                continue
            idx.append(t)
            vals.append(val)
        if len(vals) < 2:
            return None
        s = pd.Series(vals, index=pd.to_datetime(idx, utc=True)).sort_index()
        return s[~s.index.duplicated(keep="last")]

    @staticmethod
    def _to_cm_pnp(s: pd.Series, station_key: str) -> pd.Series:
        """Einheiten-Plausibilisierung und Umrechnung nach cm ueber PNP."""
        med = float(s.median())
        lo, hi = PLAUSIBLE_CM_PNP
        if -15.0 < med < 15.0:      # vermutlich Meter (ueber NHN o.ae.)
            s = s * 100.0
            med = float(s.median())
        if -600.0 < med < lo:       # vermutlich cm ueber NHN -> PNP = NHN - 5 m
            s = s + 500.0
            med = float(s.median())
        s = s + BSH_DATUM_OFFSET_CM.get(station_key, 0.0)
        if not (lo < float(s.median()) < hi):
            raise RuntimeError(
                f"BSH-Werte fuer {station_key} unplausibel (Median {med:.1f}). "
                f"Bezugshorizont pruefen (--explore) und BSH_DATUM_OFFSET_CM setzen."
            )
        return s
