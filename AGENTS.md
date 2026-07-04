# AGENTS.md

Anleitung für KI-Agenten (und Menschen), die in diesem Repo arbeiten.

## Was dieses Repo tut

Wasserstandsvorhersage für **Overwerder** (Tideelbe, Elbe-km ≈ 605,3):
BSH-Kurvenvorhersagen der Pegel **Zollenspieker** (km 598,3, stromauf) und
**Hamburg St. Pauli / Fischmarkt** (km 623,1, stromab) werden zeitversetzt und
gewichtet auf den Zielort interpoliert. Kalibriert wird am Messpegel **Over**
(PEGELONLINE), der direkt gegenüber Overwerder liegt. Methodik: `PLAN_MWP.md`.

## Struktur

```
wasserstand_overwerder/
  config.py       Elbe-km, Stationsnamen, API-Basis-URLs, Datum-Offsets, Archiv-UUIDs
  pegelonline.py  Beobachtungen (W, cm über PNP) von PEGELONLINE (rollierende 31 Tage)
  history.py      Langzeitarchiv seit 2000 (minuetlich) -> jaehrl. Parquet-Dataset
  hfhub.py        Upload des Parquet-Datasets zu Hugging Face (optionales Extra "hf")
  bsh.py          BSH-Vorhersagen via OGC API Features (Laufzeit-Discovery)
  model.py        Interpolation (Params, interpolate, calibrate, recent_bias_cm)
  sturmflut.py    Thw-Erkennung + BSH-Klassifikation + Trend (netzfrei, testbar)
  plot.py         matplotlib-Plot
  webexport.py    baut data.json fuer die Web-App (netzfrei, build_payload)
calibrate.py      CLI: fittet tau/Gewichte/Offset gegen Pegel Over -> params.json
forecast.py       CLI: erzeugt out/overwerder_forecast.{csv,png}; --explore
analyse_sturmfluten.py CLI: Sturmflut-EDA (Haeufigkeit/Saison/Trend) -> docs/sturmflut_*.png
export_web.py     CLI: erzeugt web/public/data.json (BSH + PEGELONLINE) fuers Frontend
build_history.py  CLI: voller Backfill des jaehrl. Parquet-Archivs (einmalig)
update_history.py CLI: inkrementelles Monatsupdate (nur juengste year=YYYY -> HF)
web/              React+Vite+TS Single-Page-App (Recharts), Deploy nach GitHub Pages
tests/test_model.py      Synthetik-Tests (netzwerkfrei)
tests/test_sturmflut.py  Synthetik-Tests fuer Thw/Klassifikation/Trend (netzwerkfrei)
tests/test_webexport.py  Struktur-Tests fuer data.json (netzwerkfrei)
tests/test_history.py    Parsing/Parquet-Tests fuers Archiv (netzwerkfrei)
tests/test_hfhub.py      Dataset-Card/Upload-Pattern-Tests (netzwerkfrei)
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
uv run python analyse_sturmfluten.py     # Sturmflut-EDA -> docs/sturmflut_*.png (braucht Netz/HF)
uv run python export_web.py --out web/public          # data.json (braucht Netz)
uv run python export_web.py --demo --out web/public   # data.json synthetisch (kein Netz)
uv run python build_history.py --start 2000-01-01 --end 2000-01-08 \
    --stations over zollenspieker         # Parquet-Archiv (braucht Netz), kleiner Test
uv sync --extra hf                        # huggingface_hub fuer den HF-Upload
HF_TOKEN=... uv run python build_history.py --start 2000-01-01 --end 2026-07-01 \
    --stations over zollenspieker --hf-repo   # einmaliger Backfill -> Hugging Face
HF_TOKEN=... uv run python update_history.py  # inkrementelles Monatsupdate -> HF
cd web && npm ci && npm run build        # Frontend bauen (Typecheck + Vite)
cd web && npm run dev                    # Frontend lokal (data.json vorher erzeugen)
```

## Wichtige Konventionen & Fallstricke

- **Einheiten:** intern immer **cm über PNP** (PNP der Tideelbe-Pegel =
  NHN − 5,00 m); Zeitindizes immer **tz-aware UTC**, Ausgabe zusätzlich in
  Europe/Berlin. Neue Datenquellen zuerst nach cm über PNP normieren.
- **Sturmflut-Schwellen sind St.-Pauli-bezogen:** BSH-Klassen und die Marke
  "Wasser auf dem Gelaende" (St. Pauli NN+3,0 m) gelten am Pegel St. Pauli, nicht
  an Over. `sturmflut.align_to_stpauli` uebersetzt sie ueber Datums-Anker
  (`config.ST_PAULI_ANKER_NN_M` + MThw-Paar) linear auf Over (cm ueber PNP). Neue
  Schwellen nicht direkt an Over-MThw haengen. Methodik/Grafiken:
  `docs/STURMFLUT_EDA.md`; Web-Chart zeigt die Gelaende-Linie
  (`WASSER_AUF_GELAENDE_OVER_CM`).
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
- PEGELONLINE-REST-API (`pegelonline.py`) liefert max. die letzten **31 Tage**
  (`--days` entsprechend). Fuer aeltere Daten das **Langzeitarchiv** nutzen:
  `history.fetch_history` / `build_history.py` (minuetliche Rohdaten ab
  2000-01-01, ZIP+CSV ueber `historische-zeitreihen/prepare-download`).
- **Langzeitarchiv nur fuer WSV-Pegel:** Over und Zollenspieker haben das
  "Download langfristiger Wasserstaende"-Archiv, der HPA-Pegel **Hamburg
  St. Pauli nicht** (Server-Fehlerseite -> `ArchiveNotAvailable`).
  `build_history.py` zieht St. Pauli daher fuer Zeitraeume < 31 Tage per
  REST-Fallback; historisch (vor >31 Tagen) fehlt St. Pauli in dieser Quelle.
- **Archiv-Zeitstempel** stehen in gesetzlicher Zeit (MEZ/MESZ mit Sommerzeit),
  nicht in Winterzeit wie die taeglichen `down.csv`-Dateien — `history.py`
  lokalisiert nach Europe/Berlin (`ambiguous="infer"`) und gibt UTC zurueck.
- **Parquet-Archiv:** jaehrlich partitioniert (`year=YYYY/`), tidy-long
  (`time, station, w_cm_pnp, year`), **zstd**-komprimiert (~110 MB fuers
  Gesamtarchiv Over+Zollenspieker); erneute Aufrufe **haengen an**
  (`existing_data_behavior="overwrite_or_ignore"`), also taeglich/monatlich
  erweiterbar. Ueberlappende Zeitraeume koennen Duplikate erzeugen.
- **Hosting = Hugging Face Dataset:** Default-Repo
  `aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000`.
  `huggingface_hub` ist ein **optionales** Extra (`uv sync --extra hf`, Gruppe
  `hf`), lazy importiert; Auth ueber `HF_TOKEN`.
  - **Einmalig:** `build_history.py --hf-repo` (voller Backfill seit 2000,
    `replace_years=None` -> spiegelt das ganze Dataset).
  - **Laufend:** `update_history.py` (inkrementell) baut nur laufendes Jahr +
    1 Vorjahr neu und ersetzt via `replace_years` **genau diese**
    `year=YYYY/`-Partitionen; aeltere Jahre bleiben unberuehrt. Idempotent,
    sauber ueber Jahreswechsel.
  - Workflow `.github/workflows/history.yml`: monatlich inkrementell (Cron),
    `workflow_dispatch` mit `mode=full` fuer den Backfill; Repo-Secret
    `HF_TOKEN`. Nicht ins Git-Repo committen (zu gross).
- Sprache: Doku/CLI-Ausgaben auf Deutsch, Bezeichner im Code auf Englisch.

## Tests vor dem Commit

`uv run pytest` muss durchlaufen (ebenso `uv run ruff check .`). Für reine
Logikänderungen keine Netzabhängigkeit einführen.
