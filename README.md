# Wasserstandsvorhersage Overwerder Bogen 79

Vorhersage des Elbe-Wasserstands für **Overwerder Bogen 79** (Wochenendhaus­siedlung
Overwerder, Tideelbe bei Elbe-km ≈ 605,3) aus den **BSH-Wasserstandsvorhersagen**
der Pegel **Zollenspieker** (km 598,3) und **Hamburg St. Pauli / Fischmarkt**
(km 623,1) — kalibriert an Beobachtungen des Messpegels **Over** (PEGELONLINE),
der direkt gegenüber liegt.

Plan und Methodik: [PLAN_MWP.md](PLAN_MWP.md)

## Schnellstart

Das Projekt nutzt [uv](https://docs.astral.sh/uv/) für Abhängigkeiten und
Umgebung (`pyproject.toml` + `uv.lock`).

```bash
uv sync                       # Abhängigkeiten installieren (+ .venv anlegen)

# Parameter (Tide-Laufzeit, Gewichte, Offset) an Pegel Over kalibrieren:
uv run python calibrate.py --days 30 --out params.json

# Vorhersage erzeugen (CSV + Plot in out/):
uv run python forecast.py --params params.json --out out/ --bias-correct
```

Ohne `uv` funktioniert auch `pip install -e .` und dann `python forecast.py`.
Ohne `params.json` rechnet `forecast.py` mit entfernungsgewichteten Defaults.
Falls sich die BSH-API-Struktur ändert: `uv run python forecast.py --explore`.

## Tests & Lint

```bash
uv run pytest                 # Tests (kein Netz nötig)
uv run ruff check .           # Lint
uv run ruff format .          # Formatierung
```

## Datenquellen

- [BSH Wasserstandsvorhersage](https://wasserstand.bsh.de) /
  [OGC-API](https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast) (CC BY 4.0)
- [PEGELONLINE](https://www.pegelonline.wsv.de) (WSV, Beobachtungen der letzten 31 Tage)
