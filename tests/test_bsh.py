"""Netzfreier Test des BSH-Discovery-/Parsing-Clients.

Bildet die reale Struktur der BSH-OGC-API nach (ein Feature je Pegel mit
zwei eingebetteten Listen: dichte `curve` mit String-Werten und grobe
`high_water_low_water` mit numerischem `forecast_value`) und mockt
`BSHClient._get_json`, damit kein Netz noetig ist. Prueft, dass die
Heuristik die dichte Kurve waehlt und String-Werte nach cm ueber PNP liest.

Hintergrund (Live-Discovery gegen gdi.bsh.de, Juli 2026): eine Collection
`waterlevelforecastdata`, Stationsname in `gauge_label`, Kurvenwerte als
Strings, Vorhersagefeld `automated_curve_forecast` nur in der Zukunft,
`measurement` nur in der Vergangenheit.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder.bsh import BSHClient


def _curve(n_past: int = 6, n_future: int = 30) -> list[dict]:
    """Kurve wie bei der BSH: Werte als Strings, Vergangenheit hat
    `measurement`, Zukunft `automated_curve_forecast`; `tidal_prediction`
    (500) ist immer da und darf nur als letzter Fallback genutzt werden."""
    pts = []
    for i in range(n_past):
        ts = f"2026-07-03 {6 + i // 6:02d}:{(i % 6) * 10:02d}:00+02:00"
        pts.append({"timestamp": ts, "tidal_prediction": "500", "measurement": "550"})
    for i in range(n_future):
        h = 7 + (i // 6)
        ts = f"2026-07-03 {h:02d}:{(i % 6) * 10:02d}:00+02:00"
        pts.append(
            {
                "timestamp": ts,
                "tidal_prediction": "500",
                "automated_curve_forecast": "650",
            }
        )
    return pts


def _high_low() -> list[dict]:
    """Grobe Tidescheitel mit numerischem forecast_value (=999), das die
    alte Heuristik faelschlich gewaehlt haette."""
    return [
        {
            "event_timestamp": "2026-07-03 09:18:00+02:00",
            "event": "NW",
            "tidal_prediction_value": "349",
            "forecast_value": 999,
        },
        {
            "event_timestamp": "2026-07-03 15:07:00+02:00",
            "event": "HW",
            "tidal_prediction_value": "663",
            "forecast_value": 999,
        },
    ]


def _feature(label: str) -> dict:
    return {
        "properties": {
            "gauge_label": label,
            "gaugezero_relative_to_nhn": -498.0,
            "chartdatum_relative_to_gaugezero": 287.0,
            "mean_high_water": 641.0,
            "operator_gauge_id": "9510060",
            "forecast_timestamp": "2026-07-03 07:19:22+02:00",
            "high_water_low_water": _high_low(),
            "curve": _curve(),
        }
    }


_COLLECTIONS = {
    "collections": [
        {"id": "waterlevelforecastdata", "title": "Water level forecast data"}
    ]
}
_ITEMS = {
    "features": [
        _feature("Cuxhaven, Steubenhoeft, Elbe"),  # Decoy
        _feature("Hamburg, Zollenspieker, Elbe"),
        _feature("Hamburg, St. Pauli, Elbe"),
    ],
    "links": [],
}


def _mock_client() -> BSHClient:
    c = BSHClient()

    def fake_get_json(url, **params):
        if url.endswith("/collections"):
            return _COLLECTIONS
        if url.endswith("/items"):
            return _ITEMS
        raise AssertionError(f"unerwartete URL: {url}")

    c._get_json = fake_get_json  # type: ignore[assignment]
    return c


def test_forecast_uses_dense_curve_not_extremes():
    c = _mock_client()
    s = c.forecast("zollenspieker")
    assert s.name == "zollenspieker"
    assert len(s) == 36, len(s)  # 6 + 30 Kurvenpunkte, nicht 2
    # Vergangenheit = Messung (550); der Vorhersageteil dockt stetig an und
    # klingt zur rohen Vorhersage (650) ab -> Werte im Band [550, 650].
    assert s.min() >= 550.0 - 1e-6 and s.max() <= 650.0 + 1e-6
    assert float(s.iloc[:6].max()) == 550.0  # reine Messung
    assert float(s.iloc[-1]) > 640.0  # weit draussen wieder ~rohe Vorhersage
    assert 999.0 not in set(s.values)  # nicht die Tidescheitel
    assert 500.0 not in set(s.values)  # tidal_prediction nur Fallback
    assert s.index.tz is not None  # tz-aware UTC
    assert str(s.index.tz) == "UTC"
    assert s.index.is_monotonic_increasing


def test_forecast_docks_smoothly_no_kink():
    """Die Naht Messung -> Vorhersage darf keinen Sprung mehr zeigen."""
    c = _mock_client()
    s = c.forecast("zollenspieker")
    steps = s.diff().dropna().abs()
    # Ohne Andockung waere der Naht-Sprung 100 cm (550 -> 650); jetzt glatt.
    assert steps.max() < 15.0, steps.max()


def test_forecast_station_matching():
    c = _mock_client()
    up = c.forecast("zollenspieker")
    down = c.forecast("st_pauli")
    assert len(up) == len(down) == 36
    # beide plausibel in cm ueber PNP
    for s in (up, down):
        assert 50.0 < float(s.median()) < 1300.0


def test_parse_embedded_docks_forecast_to_measurement():
    c = _mock_client()
    s = c._parse_embedded(_curve(n_past=2, n_future=2))
    vals = list(s.values)
    assert vals[:2] == [550.0, 550.0]  # Vergangenheit = Messung
    # erster Vorhersagepunkt dockt exakt an die letzte Messung an (offset0=-100)
    assert abs(vals[2] - 550.0) < 1e-6
    # danach klingt die Korrektur Richtung roher Vorhersage (650) ab
    assert 550.0 < vals[3] < 650.0
    assert vals[3] > vals[2]


def test_value_rank_prefers_forecast_over_measurement():
    assert BSHClient._value_rank("automated_curve_forecast") == 0
    assert BSHClient._value_rank("measurement") == 2
    assert BSHClient._value_rank("tidal_prediction") == 3
    assert BSHClient._value_rank("forecast_value") == 0


def test_as_float_handles_strings():
    assert BSHClient._as_float("478") == 478.0
    assert BSHClient._as_float("1,5") == 1.5
    assert BSHClient._as_float(433) == 433.0
    assert BSHClient._as_float(True) is None
    assert BSHClient._as_float("Wasserstandsvorhersage") is None
    assert BSHClient._as_float(None) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("Alle BSH-Tests bestanden.")
