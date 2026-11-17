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
  alerts.py       Event-Erkennung (Gelaende/Sturmflut) + Issue-Abgleich (netzfrei)
  ghissues.py     schlanker GitHub-Issues-Client (REST) fuer die Alarm-Issues
  plot.py         matplotlib-Plot
  webexport.py    baut data.json fuer die Web-App (netzfrei, build_payload)
  inundation.py   DGM1 (LGV) laden, Ueberlaufhoehe + Fliessweg je Rasterzelle
  buildings.py    LoD2-Gebaeude (LGV): Grundriss, Bodenhoehe, Hausnr., Ueberlaufhoehe
  inundation_web.py Gelaende-Asset (web/public/overhaken.json) fuer die Web-Karte
calibrate.py      CLI: fittet tau/Gewichte/Offset gegen Pegel Over -> params.json
forecast.py       CLI: erzeugt out/overwerder_forecast.{csv,png}; --explore
analyse_sturmfluten.py CLI: Sturmflut-EDA (Haeufigkeit/Saison/Trend) -> docs/sturmflut_*.png
export_web.py     CLI: erzeugt web/public/data.json (BSH + PEGELONLINE) fuers Frontend
alert_issues.py   CLI: liest data.json, legt/aktualisiert Ueberflutungs-Issues (GitHub)
inundation.py     CLI: Gelaende-Asset der Overhaken-Karte -> web/public/overhaken.json
build_history.py  CLI: voller Backfill des jaehrl. Parquet-Archivs (einmalig)
update_history.py CLI: inkrementelles Monatsupdate (nur juengste year=YYYY -> HF)
web/              React+Vite+TS Single-Page-App (Recharts), Deploy nach GitHub Pages
tests/test_model.py      Synthetik-Tests (netzwerkfrei)
tests/test_sturmflut.py  Synthetik-Tests fuer Thw/Klassifikation/Trend (netzwerkfrei)
tests/test_webexport.py  Struktur-Tests fuer data.json (netzwerkfrei)
tests/test_history.py    Parsing/Parquet-Tests fuers Archiv (netzwerkfrei)
tests/test_hfhub.py      Dataset-Card/Upload-Pattern-Tests (netzwerkfrei)
tests/test_surge_events.py Ereignis-Kurven fuer die Karte (netzwerkfrei)
tests/test_alerts.py     Event-Erkennung + Issue-Abgleich (plan), netzwerkfrei
```

Die Web-App ist statisch: `export_web.py` schreibt `data.json`, das React-Frontend
lädt nur diese Datei. `web/public/data.json` wird **nicht eingecheckt** (`.gitignore`):
Der Workflow `.github/workflows/deploy.yml` erzeugt sie stündlich live neu, baut `web/`
und deployt nach GitHub Pages. Für lokalen Dev: `export_web.py --demo` (synthetisch,
kein Netz).

**Überflutungs-Alarm (Issues):** Derselbe Workflow ruft nach `export_web.py`
`alert_issues.py` auf. Zeigt die Overwerder-Vorhersage **Wasser auf dem Gelände**
(Scheitel ≥ `WASSER_AUF_GELAENDE_OVER_CM`), wird **ein** GitHub-Issue pro Event
(Sturm-Cluster, 36 h) angelegt und `@aaronspring` getaggt. Bei jeder Stufen-
Änderung (Sturmflut/schwere/sehr schwere, hoch **oder** runter) folgt ein
Kommentar mit erneutem Tag; ist das Event nicht mehr auf dem Gelände (Entwarnung)
oder der Scheitel vorbei, wird kommentiert und das Issue geschlossen. Der Abgleich
ist zustandslos: offene Issues mit Label `wasserstand-alert` tragen den Event-
Zustand als Marker im Body, `alerts.plan` matcht per Zeitfenster-Überlappung. Der
Schritt braucht `issues: write` + `GITHUB_TOKEN` und blockiert den Deploy nicht
(`continue-on-error`). Logik netzfrei/testbar in `alerts.py` (`tests/test_alerts.py`).

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
uv run python alert_issues.py --data web/public/data.json --dry-run  # Alarm-Plan zeigen (kein Netz/Token)
uv run python build_history.py --start 2000-01-01 --end 2000-01-08 \
    --stations over zollenspieker         # Parquet-Archiv (braucht Netz), kleiner Test
uv sync --extra hf                        # huggingface_hub fuer den HF-Upload
HF_TOKEN=... uv run python build_history.py --start 2000-01-01 --end 2026-07-01 \
    --stations over zollenspieker --hf-repo   # einmaliger Backfill -> Hugging Face
HF_TOKEN=... uv run python update_history.py  # inkrementelles Monatsupdate -> HF
uv sync --extra gelaende                  # rasterio/remotezip/scikit-image fuers DGM1
uv run python inundation.py               # Karten-Asset + Luftbild (eingecheckt; Netz: LGV)
uv run python export_web.py --demo --demo-surge-cm 220 --out web/public  # Demo mit Sturmflut fuer die Karte
uv run python export_surge_events.py      # Top-Sturmflut-Kurven -> web/public/surge_events.json (Netz/HF, Extra hf)
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
  (`WASSER_AUF_GELAENDE_OVER_CM`) dauerhaft und die BSH-Klassen-Schwellen
  (`STURMFLUT_STUFEN_OVER_CM`: Sturmflut/schwere/sehr schwere) per Legenden-
  Toggle „Sturmflut-Stufen" (Default aus, da weit ueber Normaltide).
- **Mondphasen-Leiste:** ueber dem Chart laeuft eine zweite X-Achse
  (`xAxisId="moon"` in `web/src/Chart.tsx`) mit je einem Emoji pro sichtbarem
  Kalendertag, gesetzt in die Mitte des sichtbaren Tagesanteils; der Tag mit
  "jetzt" ist hervorgehoben. Phase netzfrei aus `web/src/moon.ts`. Die
  Achsenhoehe haelt bewusst Platz fuer die absolut positionierten Zoom-Buttons
  (`.chart-controls`) frei — beim Aendern nicht knapper machen, sonst
  ueberdecken die Buttons die Emojis.
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
  2000-01-01, ZIP+CSV ueber `/gast/download/prepare` -> JSON `downloadUrl`; Tage inkl. Ende).
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
- **Gelaende (DGM1, `inundation.py`):** Methodik in `docs/INUNDATION.md`.
  Python erzeugt nur das statische Asset der Web-Karte; Zeitpunkte und
  Tiefen rechnet der Browser. Over-PNP ist **-5,098 m NHN** (`config.OVER_PNP_NHN_M`),
  nicht -5,00. Das DGM1 fuellt Wasserflaechen mit Platzhaltern (Elbe 2,00 m,
  See 1,00 m) -> `water_fill_mask`, sonst wirkt die Elbe als 2-m-Schwelle.
  Download-ZIP liegt auf `archiv.transparenz.hamburg.de` (alte
  daten-hamburg.de-Links 404); Kacheln per HTTP-Range, Cache `out/dgm1/`.
  Im ZIP fehlende Kacheln (Niedersachsen) stehen in `out/dgm1/absent.txt`.
  Extra `gelaende` ist optional und wird lazy importiert. Ausschnitt,
  Beschriftungen, Versickerung (10 cm/h) und Fliessgeschwindigkeit (0,3 m/s)
  in `config.INUNDATION_*`.
  Gebaeude: LoD2-DE (CityGML 1.0, `config.LOD2_URL`); im Vorland haben fast
  keine Gebaeude eine ALKIS-Hausnummer -> laufende Nummer `nr` (NW->SO) +
  `alkis_id`; Nummern aendern sich, wenn Gebaeude hinzukommen. Die Web-Karte
  zeigt nur Gebaeude aus `config.OVERHAKEN_PARZELLEN` (ALKIS-Kennung ->
  Parzellen-Nummer laut Lageplan-Schild der Kolonie, 37 Gebaeude); neue
  Gebaeude dort per `alkis_id` eintragen. Gebaeude ohne LoD2-Grundriss
  (Wohnwagen 136) stehen als Ecken in `config.OVERHAKEN_MANUELLE_GEBAEUDE`
  (Kennung `manuell-*`, ebenfalls in `OVERHAKEN_PARZELLEN` eintragen).
- **Overhaken-Karte (Web):** `web/src/OverhakenMap.tsx` zeigt die Kolonie zum
  Zeitpunkt der per Klick fixierten Ablese-Linie (sonst Hover im Chart, sonst
  jetzt); Hover auf der Karte zeigt Wassertiefe/Gelaende an der Stelle;
  Zoom/Verschieben ueber `web/src/useZoom.ts` (CSS-Transform auf `.map-layers`;
  +/-, Strg+Mausrad, Pinch), Parzellen-Nummern erst ab 1,4 px/m;
  Klick auf eine Top-10-/Sturmflut-Stufen-Linie im Chart setzt
  `cursor.scenario` -> Karte zeigt den Scheitel aus
  `web/public/surge_events.json` (eingecheckt, `export_surge_events.py`, Extra
  `hf`; Stufen: Kurve der naechstgelegenen Top-Sturmflut, auf die Stufe
  verschoben); erneuter Klick oder "Zurueck zur Vorhersage" loest es;
  Kopplung ueber `web/src/cursor.ts` (kein App-Re-Render pro Mausbewegung).
  Tiefe wird im Browser gerechnet (Badewanne mit Verbindung, Stauwasser
  versickert, Fliesszeit je Zelle) aus dem statischen, eingecheckten
  `web/public/overhaken.json` (2-m-Raster, Over-PNP -5,098 m) und
  `overhaken_dop.jpg`. Nach Aenderung von `config.INUNDATION_*`,
  `OVERHAKEN_BBOX` oder `DOP_*` mit `inundation.py` neu erzeugen.
- Sprache: Doku/CLI-Ausgaben auf Deutsch, Bezeichner im Code auf Englisch.

## Tests vor dem Commit

`uv run pytest` muss durchlaufen (ebenso `uv run ruff check .`). Für reine
Logikänderungen keine Netzabhängigkeit einführen.
