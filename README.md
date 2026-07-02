# Wasserstandsvorhersage Overwerder Bogen 79

Vorhersage des Elbe-Wasserstands für **Overwerder Bogen 79** (Wochenendhaus­siedlung
Overwerder, Tideelbe bei Elbe-km ≈ 605,3) aus den **BSH-Wasserstandsvorhersagen**
der Pegel **Zollenspieker** (km 598,3) und **Hamburg St. Pauli / Fischmarkt**
(km 623,1) — kalibriert an Beobachtungen des Messpegels **Over** (PEGELONLINE),
der direkt gegenüber liegt.

Plan und Methodik: [PLAN_MWP.md](PLAN_MWP.md)

## Schnellstart

```bash
pip install -r requirements.txt

# Parameter (Tide-Laufzeit, Gewichte, Offset) an Pegel Over kalibrieren:
python calibrate.py --days 30 --out params.json

# Vorhersage erzeugen (CSV + Plot in out/):
python forecast.py --params params.json --out out/ --bias-correct
```

Ohne `params.json` rechnet `forecast.py` mit entfernungsgewichteten Defaults.
Falls sich die BSH-API-Struktur ändert: `python forecast.py --explore`.

## Tests

```bash
python tests/test_model.py
```

## Datenquellen

- [BSH Wasserstandsvorhersage](https://wasserstand.bsh.de) /
  [OGC-API](https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast) (CC BY 4.0)
- [PEGELONLINE](https://www.pegelonline.wsv.de) (WSV, Beobachtungen der letzten 31 Tage)
