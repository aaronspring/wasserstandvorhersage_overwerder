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
calibrate.py      CLI: fittet tau/Gewichte/Offset gegen Pegel Over -> params.json
forecast.py       CLI: erzeugt out/overwerder_forecast.{csv,png}; --explore
tests/test_model.py  Synthetik-Tests (netzwerkfrei)
```

## Kommandos

```bash
pip install -r requirements.txt
python tests/test_model.py            # Tests (kein Netz noetig, < 1 min)
python calibrate.py --days 30         # braucht Netz (PEGELONLINE)
python forecast.py --params params.json --out out/   # braucht Netz (BSH)
python forecast.py --explore          # BSH-API-Struktur dumpen
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

`python tests/test_model.py` muss durchlaufen. Für reine Logikänderungen keine
Netzabhängigkeit einführen.
