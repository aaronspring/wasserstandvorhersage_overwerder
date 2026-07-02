# Plan: Wasserstandsvorhersage Overwerder Bogen 79 (MWP)

## Ziel

Eine Wasserstandsvorhersage für **Overwerder Bogen 79** (Wochenendhaussiedlung
Overwerder, Vier- und Marschlande, Tideelbe bei Elbe-km ≈ 605), abgeleitet aus den
**BSH-Wasserstandsvorhersagen** für die Pegel **Zollenspieker** und
**Hamburg St. Pauli** (Landungsbrücken/Fischmarkt). Minimal Working Product (MWP):
nur Python-Skripte, die Daten holen und eine Vorhersage-Zeitreihe + Plot erzeugen.

## Lage / Geometrie

| Ort | Elbe-km | Rolle |
|---|---|---|
| Zollenspieker | 598,3 | BSH-Vorhersage (stromauf von Overwerder) |
| **Overwerder** | **≈ 605,3** | Zielort (gegenüber der Ortschaft Over) |
| Over (Pegel) | 605,3 | PEGELONLINE-Messpegel direkt am Zielort → Kalibrierung/Validierung |
| Bunthaus | 609,8 | optionaler Zusatzpegel (nicht im MWP) |
| Hamburg St. Pauli | 623,1 | BSH-Vorhersage (stromab, "Fischmarkt") |

Overwerder liegt zwischen den beiden Vorhersagepegeln, ca. 28 % der Strecke von
Zollenspieker Richtung St. Pauli. Glücksfall: der Messpegel **Over** liegt praktisch
am Zielort — er liefert zwar keine Vorhersage, aber Beobachtungen zum Kalibrieren.

## Datenquellen

1. **BSH Wasserstandsvorhersage** (CC BY 4.0):
   OGC-API-Features-Dienst `https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast`
   → Kurvenvorhersagen u. a. für Hamburg St. Pauli und Zollenspieker
   (Web-Ansicht: `wasserstand.bsh.de`).
   Da die Collection-/Feldnamen nicht offiziell dokumentiert sind, macht der Client
   eine **Laufzeit-Discovery** (`/collections` → Heuristik für Stations- und
   Vorhersage-Collection) und bietet `--explore` zum Inspizieren der API.
2. **PEGELONLINE REST-API** (`https://www.pegelonline.wsv.de/webservices/rest-api/v2`):
   Beobachtungen (Zeitreihe `W`, cm über PNP, letzte ≤ 31 Tage) für
   ZOLLENSPIEKER, HAMBURG ST. PAULI und OVER — für Kalibrierung, Bias-Korrektur
   und Validierung. PNP der Tideelbe-Pegel: NHN −5,00 m (wird zur Laufzeit aus der
   API gelesen).

## Methode (MWP)

Zeitversetzte, gewichtete Interpolation zwischen den beiden Vorhersagepegeln:

```
O(t) = a_up · Z(t + f·τ)  +  a_down · P(t − (1−f)·τ)  +  c
```

- `Z` = Zollenspieker, `P` = St. Pauli, `O` = Overwerder
- `f` = Streckenanteil Zollenspieker→Overwerder ≈ 0,28
- `τ` = Laufzeit der Tidewelle St. Pauli → Zollenspieker (Default 60 min,
  wird kalibriert). Die Tide läuft stromauf: sie erreicht St. Pauli zuerst,
  Overwerder ca. `(1−f)·τ` später, Zollenspieker weitere `f·τ` später.
- Startwerte für die Gewichte: entfernungsgewichtet (`a_up ≈ 0,72`, `a_down ≈ 0,28`, `c = 0`).
- **Kalibrierung** (`calibrate.py`): Gitternsuche über `τ` + lineare Regression
  (`a_up`, `a_down`, `c`) gegen die letzten ~30 Tage Beobachtung am Pegel **Over**;
  Parameter werden als `params.json` gespeichert.
- **Bias-Korrektur** (optional in `forecast.py`): mittleres Residuum
  Modell − Beobachtung Over der letzten Stunden wird von der Vorhersage abgezogen.

## Komponenten

```
PLAN_MWP.md                       ← dieser Plan
requirements.txt                  ← requests, pandas, numpy, matplotlib
wasserstand_overwerder/
  config.py                       ← Elbe-km, Stationsnamen, Defaults
  pegelonline.py                  ← Beobachtungen (W) von PEGELONLINE
  bsh.py                          ← BSH-Vorhersagen (OGC API, Discovery + --explore)
  model.py                        ← Interpolation, Kalibrierung, Metriken
  plot.py                         ← Ergebnis-Plot (matplotlib)
calibrate.py                      ← CLI: Parameter aus Beobachtungen fitten → params.json
forecast.py                       ← CLI: Vorhersage erzeugen → CSV + PNG
tests/test_model.py               ← Synthetik-Test (M2-Tide): Kalibrierung findet
                                    bekannte Parameter wieder
```

## Nutzung

```bash
pip install -r requirements.txt

# 1) einmalig (und gelegentlich neu): Parameter an Pegel Over kalibrieren
python calibrate.py --days 30 --out params.json

# 2) Vorhersage erzeugen
python forecast.py --params params.json --out out/
#    → out/overwerder_forecast.csv  (UTC + Lokalzeit, cm über PNP, m über NHN)
#    → out/overwerder_forecast.png

# BSH-API-Struktur ansehen (falls sich Feldnamen ändern):
python forecast.py --explore
```

## Annahmen & Grenzen

- Der BSH-Dienst ist aus der Entwicklungs-Sandbox nicht erreichbar (Egress-Policy);
  Collection-/Feldnamen werden deshalb zur Laufzeit heuristisch erkannt. Falls die
  Heuristik fehlschlägt: `--explore` ausführen und Mapping in `config.py` eintragen.
- Einheiten/Bezugshorizont der BSH-Vorhersage werden per Plausibilitätsprüfung
  (Wertebereich) gegen cm-über-PNP geprüft; ggf. `datum_offset_cm` in `config.py` setzen.
- Lineares Modell: bei Sturmfluten und hohem Oberwasser (Abfluss Neu Darchau) sind
  Laufzeit und Amplitude nichtlinear → Residuen werden bei der Kalibrierung
  ausgewiesen; Bias-Korrektur fängt langsame Fehler ab.
- Vorhersagehorizont = Horizont der BSH-Kurvenvorhersage.

## Nächste Schritte (nach dem MWP)

1. Validierungsreport: Vorhersage vs. Pegel Over über mehrere Wochen archivieren.
2. Oberwasser (Q Neu Darchau) und Windstau als Zusatzprädiktoren.
3. Pegel Bunthaus als dritten Stützpegel einbeziehen.
4. Automatisierung (Cron/GitHub Actions) + einfache HTML-Ansicht.
