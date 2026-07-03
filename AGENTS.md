# AGENTS.md

Anleitung für KI-Agenten (und Menschen), die in diesem Repo arbeiten.

## Was dieses Repo tut

Wasserstandsvorhersage für **Overwerder Bogen 79** (Tideelbe, Elbe-km ≈ 605,3):
BSH-Kurvenvorhersagen der Pegel **Zollenspieker** (km 598,3, stromauf) und
**Hamburg St. Pauli / Fischmarkt** (km 623,1, stromab) werden zeitversetzt und
gewichtet auf den Zielort interpoliert. Kalibriert wird am Messpegel **Over**
(PEGELONLINE), der direkt gegenüber Overwerder liegt. Methodik: `PLAN_MWP.md`.

## Struktur

```
wasserstand_overwerder/
  config.py       Elbe-km, Stationsnamen, API-Basis-URLs, Datum-Offsets
  pegelonline.py  Beobachtungen (W, cm über PNP) von PEGELONLINE
  bsh.py          BSH-Vorhersagen via OGC API Features (Laufzeit-Discovery)
  model.py        Interpolation (Params, interpolate, calibrate, recent_bias_cm)
  plot.py         matplotlib-Plot
  webexport.py    baut data.json fuer die Web-App (netzfrei, build_payload)
calibrate.py      CLI: fittet tau/Gewichte/Offset gegen Pegel Over -> params.json
forecast.py       CLI: erzeugt out/overwerder_forecast.{csv,png}; --explore
export_web.py     CLI: erzeugt web/public/data.json (BSH + PEGELONLINE) fuers Frontend
web/              React+Vite+TS Single-Page-App (Recharts), Deploy nach GitHub Pages
tests/test_model.py      Synthetik-Tests (netzwerkfrei)
tests/test_webexport.py  Struktur-Tests fuer data.json (netzwerkfrei)
```

Die Web-App ist statisch: `export_web.py` schreibt `data.json`, das React-Frontend
lädt nur diese Datei. `web/public/data.json` wird **nicht eingecheckt** (`.gitignore`):
Der Workflow `.github/workflows/deploy.yml` erzeugt sie alle 6 h live neu, baut `web/`
und deployt nach GitHub Pages. Für lokalen Dev: `export_web.py --demo` (synthetisch,
kein Netz).

## Kommandos

```bash
uv sync                                  # Abhaengigkeiten (pyproject.toml/uv.lock)
uv run pytest                            # Tests (kein Netz noetig, < 1 min)
uv run ruff check . && uv run ruff format --check .   # Lint + Format
uv run python calibrate.py --days 30     # braucht Netz (PEGELONLINE)
uv run python forecast.py --params params.json --out out/   # braucht Netz (BSH)
uv run python forecast.py --explore      # BSH-API-Struktur dumpen
uv run python export_web.py --out web/public          # data.json (braucht Netz)
uv run python export_web.py --demo --out web/public   # data.json synthetisch (kein Netz)
cd web && npm ci && npm run build        # Frontend bauen (Typecheck + Vite)
cd web && npm run dev                    # Frontend lokal (data.json vorher erzeugen)
```

## Wichtige Konventionen & Fallstricke

- **Einheiten:** intern immer **cm über PNP** (PNP der Tideelbe-Pegel =
  NHN − 5,00 m); Zeitindizes immer **tz-aware UTC**, Ausgabe zusätzlich in
  Europe/Berlin. Neue Datenquellen zuerst nach cm über PNP normieren.
- **Tide-Richtung:** die Tidewelle läuft stromauf; Elbe-km wächst stromab.
  St. Pauli führt zeitlich, Zollenspieker läuft nach. Vorzeichen der
  Zeitverschiebungen in `model.interpolate` nicht "vereinfachen".
- **BSH-API:** Collection-/Feldnamen sind nicht dokumentiert und werden in
  `bsh.py` heuristisch erkannt. Bei Schema-Änderungen `--explore` nutzen und
  `config.py` (`BSH_STATION_PATTERNS`, `BSH_DATUM_OFFSET_CM`) anpassen, nicht
  die Heuristik hart verdrahten.
- **Sandbox-Hinweis:** In Claude-Code-Remote-Umgebungen sind
  `gdi.bsh.de`/`pegelonline.wsv.de` u. U. per Egress-Policy blockiert —
  Netz-Codepfade dann nur per Mock/Synthetik testen (`tests/test_model.py`).
- **Kalibrier-Identifizierbarkeit:** Bei rein sinusförmigen Testdaten ist die
  Laufzeit `tau` nicht identifizierbar; synthetische Tiden brauchen Obertiden
  (siehe `synthetic_tide` in den Tests).
- PEGELONLINE liefert max. die letzten **31 Tage** (`--days` entsprechend).
- Sprache: Doku/CLI-Ausgaben auf Deutsch, Bezeichner im Code auf Englisch.

## Tests vor dem Commit

`uv run pytest` muss durchlaufen (ebenso `uv run ruff check .`). Für reine
Logikänderungen keine Netzabhängigkeit einführen.
