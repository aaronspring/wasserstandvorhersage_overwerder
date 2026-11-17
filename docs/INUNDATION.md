# Überflutungs-Zeitpunkte Overhaken / Overwerder (DGM1)

`inundation.py` berechnet für jede 1-m-Zelle des Overwerder Vorlands, **wann**
sie bei einer Tide nass wird, wie lange sie nass bleibt und wie tief das Wasser
steht. Damit lässt sich direkt ablesen, wie die Geländehöhe einer Parzelle
den Zeitpunkt bestimmt.

Die Grafiken erzeugt `inundation.py` in `out/inundation/` (siehe Aufruf).

## Daten

| | |
|---|---|
| Gelände | **DGM1 2022**, LGV Hamburg (Laserscanning, 1 m, EPSG:25832, m ü. NHN/DHHN2016, ±15 cm) |
| Bezug | Transparenzportal „Geländemodelle Hamburg – DGM“; ZIP (1,3 GB) auf `archiv.transparenz.hamburg.de`, die alten `daten-hamburg.de`-Links liefern 404 |
| Download | per HTTP-Range nur die 1-km-Kacheln des Ausschnitts (`remotezip`), Cache `out/dgm1/` |
| Lizenz | Datenlizenz Deutschland – Namensnennung 2.0, © LGV Hamburg |
| Wasserstand | Pegel Over, cm über PNP → m NHN mit **PNP = −5,098 m NHN** (PEGELONLINE `gaugeZero`, nicht −5,00) |

| Gebäude | **LoD2-DE 2026**, LGV Hamburg (CityGML-Kacheln, Grundriss aus ALKIS, Bodenhöhe, Hausnummer falls vergeben) |

## Auflösung

| | räumlich | Höhe / Wert | Genauigkeit |
|---|---|---|---|
| Gelände DGM1 | 1 m × 1 m Raster (gerechnet wird voll in 1 m, 5,5 Mio. Zellen; das GIF zeigt 2 m) | gespeichert in 1-cm-Schritten | ±15 cm auf eindeutigen Flächen (Straßen), schlechter unter dichter Vegetation, an Böschungen und unter Brücken |
| Wasserstand Over | ein Punkt (km 605,3), gilt für das ganze Vorland | 1 cm, Rohdaten minütlich → 5-min-Mittel | Zeitauflösung des Ergebnisses 5 min |
| Gebäude LoD2 | Grundriss aus dem Kataster (cm-genau) | Bodenhöhe aus dem DGM | ALKIS-Stand je Gebäude (`Grundrissaktualitaet`) |

Was das für den Zeitpunkt heißt: Eine Höhenunsicherheit von ±15 cm
entspricht auf dem steigenden Ast etwa ±10 min, nahe dem Scheitel eher
±15–25 min. Strukturen schmaler als ~2 m, etwa Gartenzäune, Mauern oder
schmale Gräben, sind im 1-m-Raster nur unscharf oder gar nicht abgebildet.

Fallstricke im DGM1:

* Wasserflächen sind mit glatten Platzhaltern gefüllt (Elbe **2,00 m**,
  Hohendeicher See **1,00 m**). Ungefiltert wirkt die Elbe als künstliche
  2-m-Schwelle. `water_fill_mask` setzt sie auf NaN.
* Das niedersächsische Ufer fehlt (NaN). Die größte NaN-Fläche ist der Strom
  und damit die Wasserquelle.

## Methode

1. **Überlaufhöhe** je Zelle: Das ist der niedrigste Elbe-Wasserstand, bei dem
   die Zelle über einen zusammenhängenden Weg nass wird (Minimax-Pfad,
   morphologische Rekonstruktion durch Erosion, 8er-Nachbarschaft). Senken
   hinter einem Sommerdeich laufen also erst bei dessen Überströmung voll.
   Das Hinterland hinter dem Hauptdeich (Krone ≥ 8 m NHN) bleibt trocken.
2. **Auflauf**: In der Sturmtide (Tnw vor bis Tnw nach dem Scheitel) wird
   eine Zelle nass, sobald `h(t) ≥ Überlaufhöhe` gilt. Daraus ergeben sich
   Beginn und maximale Tiefe. Die Berechnung ist vektorisiert (laufendes
   Maximum + `searchsorted`), ~10 s für 5,5 Mio. Zellen.
3. **Ablauf**: Fällt der Strom, sinkt der Spiegel einer Zelle nur bis auf ihre
   Überlaufhöhe (Spiegel = `max(h, Überlaufhöhe − Ablaufrate · Δt)`). Was über
   Priele mit dem Strom verbunden ist, läuft mit der Tide ab. Abflusslose
   Mulden behalten **Stauwasser** bis zu ihrer Schwelle (`residual_depth`).
   `--drain-cm-h` lässt es mit fester Rate sinken (Versickerung im
   Sandboden, Default 10 cm/h, angenommen; 0 = bleibt stehen). Unter den
   Außenwasserstand sinkt es nicht, weil das Siel dann geschlossen ist. `depth_at` liefert die Tiefenkarte für einen beliebigen
   Zeitpunkt.
4. **Auswertung** über `OVERHAKEN_BBOX` (Vorland: Überlaufhöhe < 7 m),
   gruppiert in 0,1-m-Höhenklassen → `hoehe_zeitpunkt.csv`.
5. **Fließzeit** (nur Web-Karte): Das Wasser braucht vom Strom bis zu einer
   Zelle die Zeit *Fließweg / v* mit v = 0,3 m/s
   (`config.INUNDATION_FLOW_M_S`). Der Fließweg (`inundation.travel_distance`)
   ist der kürzeste Weg vom Strom über Zellen, die zu dem Zeitpunkt schon nass
   sind: Eine Zelle mit Überlaufhöhe *s* wird nur über Zellen mit
   Überlaufhöhe ≤ *s* erreicht (0,1-m-Stufen, 8er-Nachbarschaft, Weg im Strom
   zählt nicht). Eine Zelle mit *t* Minuten Fließzeit sieht den Wasserstand von
   vor *t* Minuten; Beginn, Spiegel und Versickerung verschieben sich also
   um *t*.

   **Warum 0,3 m/s:** Flaches Überströmen von Wiese und Parzellen, nach
   Manning *v = h^(2/3) · S^(1/2) / n* mit Wassertiefe h ≈ 0,3 m, Gefälle
   S ≈ 1 ‰ und Rauheit n ≈ 0,05 (Gras, Büsche, Zäune) → v ≈ 0,28 m/s. Die
   übliche Spanne ist 0,1–0,5 m/s, in Prielen bis ~1 m/s. Die Tidewelle in der
   Elbe selbst (~5–7 m/s) steckt schon im Pegel Over.

   **Größenordnung Overhaken:** Median 6 min, 90 % unter 20 min, maximal
   32 min im Kartenausschnitt. Da die Tide vor dem Scheitel um 30–70 cm/h
   steigt, verschiebt das den Beginn nur leicht; größer wird es nur hinter
   langen Umwegen über Sommerdeich-Kronen.

Grenzen: Es ist ein Badewannenmodell mit Verbindung. Ohne Fließzeit (CLI,
Grafiken, CSV) ist der Beginn der **früheste** mögliche Zeitpunkt; die
Web-Karte rechnet eine konstante Fließgeschwindigkeit dazu (Punkt 5), aber
keine Durchflussmengen: Ein schmaler Durchlass füllt eine große Senke in
Wirklichkeit langsamer. Dafür bräuchte es ein 2D-Modell (z. B. LISFLOOD-FP). Der Ablauf über Priele
erfolgt ebenfalls sofort, und die Ablaufrate von Stauwasser ist unbekannt und
deshalb nur ein Parameter. Die Wasserspiegellage
von Over gilt für das ganze Vorland (Over liegt gegenüber, km 605,3). Zäune,
Lauben und Sandsäcke sind nicht im DGM enthalten. Archivdaten vor 2019-11
könnten einen anderen PNP haben (`--gauge-zero`).

## Gebäude

`buildings.py` lädt die LoD2-Kacheln (Cache `out/lod2/`) und nimmt die
**502 Gebäude im Vorland**, also alle mit Überlaufhöhe < 7 m. Hausnummern
gibt es dort kaum: ALKIS führt nur **4** davon mit Adresse (Overwerder Bogen
32/76/78/80), die Lauben und Wochenendhäuser haben keine. Jedes Gebäude
bekommt deshalb eine **laufende Nummer** (`nr`, entlang des Deichs von NW
nach SO). Wo eine Hausnummer existiert, steht sie zusätzlich in der Karte
(rot) und in `gebaeude.csv`. Die ALKIS-Kennung (`alkis_id`) bleibt für den
Abgleich erhalten, z. B. mit einer Parzellenliste des Vereins.

Je Gebäude (`gebaeude.csv`): Bodenhöhe `base_m`, Überlaufhöhe `spill_m`
(niedrigste im Grundriss), `onset` (Wasser erreicht das Gebäude, MEZ),
`onset_min_rel_peak`, `hours_wet` und `depth_m` (Scheitel über
Bodenhöhe). Die Grafiken zeigen die Grundrisse überall. `gebaeude.png` ist
die nummerierte Detailkarte, eingefärbt nach Beginn, und im Querprofil sind
die geschnittenen Gebäude eingezeichnet.

Sturmflut 26.10.2026: 491 von 502 Gebäuden erreicht das Wasser, im Median
**115 min vor dem Scheitel** (Spanne 180–15 min), bei einer mittleren
Wassertiefe von **1,0 m** über Bodenhöhe (max. 2,1 m). Trocken bleiben die
höher gelegenen Gebäude am Overwerder Bogen (76/78/80, Bodenhöhe 4,6–4,9 m).

## Ergebnis Sturmflut 26.10.2026

Scheitel 957 cm PNP = 4,47 m NHN um 04:50 MEZ (Over). Auswertefläche 44 ha,
davon 95 % nass. Am Ende der Sturmtide stehen noch auf **6,6 ha** Stauwasser,
meist flache Pfützen (Median 7 cm) und vereinzelt abflusslose Gräben bis
1,8 m. Die nasse Dauer zählt Stauwasser bis zum Ende der Sturmtide mit.

| Gelände [m NHN] | Beginn vor Scheitel | nass | max. Tiefe |
|---|---|---|---|
| 2,0 | 4 h 20 min | 7,6 h | 2,4 m |
| 2,6 | 3 h 45 min | 6,0 h | 1,8 m |
| 3,0 | 3 h 20 min | 5,2 h | 1,4 m |
| 3,4 | 2 h 55 min | 4,0 h | 1,0 m |
| 3,8 | 2 h 25 min | 3,0 h | 0,6 m |
| 4,2 | 1 h 45 min | 1,7 h | 0,2 m |
| 4,4 | 1 h 20 min | 0,7 h | 0,05 m (80 % nass) |

Faustregel: Auf dem steigenden Ast bedeuten **10 cm mehr Gelände rund
6–8 min späteren Beginn und ~15 min weniger nasse Zeit**. Nahe dem Scheitel
steigt das Wasser langsamer, sodass 10 cm dort 10–15 min ausmachen und
darüber entscheiden, ob eine Parzelle überhaupt nass wird. Zum Vergleich
liegt die Marke „Wasser auf dem Gelände“ (834 cm am Pegel Over) bei
3,24 m NHN, also mitten in der typischen Parzellenhöhe von 3,0–3,6 m.

## Aufruf

```bash
uv sync --extra gelaende
uv run python inundation.py --recent --animate          # höchste Tide der letzten 31 Tage + GIF
uv run python inundation.py --recent --drain-cm-h 10    # Stauwasser sinkt 10 cm/h
uv run python inundation.py --data web/public/data.json # aktuelle Vorhersage
uv run python inundation.py --event 2013-12-06          # PEGELONLINE-Archiv
uv run python inundation.py --demo --peak-cm 960        # synthetisch
```

Ausgabe in `out/inundation/`: Grafiken `inundation.png` (Übersicht),
`gelaende.png`, `profil.png` (Querprofil A–B, Auf- und Ablauf), `verlauf.png`
(stündliche Tiefenkarten −3 h … +4 h), mit `--animate` `animation.gif`
(10-min-Schritte, ~1 min Rechenzeit). Daten: `hoehe_zeitpunkt.csv`,
`spill_m_nhn.tif`, `onset_min_rel_peak.tif`, `hours_wet.tif`, `max_depth_m.tif`,
`residual_depth_m.tif`, `gebaeude.csv`; `gebaeude.png` (nummerierte
Gebäudekarte). `--no-buildings` lässt den LoD2-Teil weg
(GeoTIFF, EPSG:25832, z. B. in QGIS über ein Luftbild legen).

## Web-Karte (Overhaken zum gewählten Zeitpunkt)

Neben dem Wasserstands-Chart der Web-App zeigt `web/src/OverhakenMap.tsx` die
Kolonie (Hütten 101–141, Elbe im Westen) zum gewählten Zeitpunkt:

- **Zeitpunkt:** Hover im Chart; ein Klick fixiert ihn („fixiert“), der nächste
  Klick löst ihn wieder; ohne beides „jetzt“.
- **Hover auf der Karte:** Wassertiefe, Geländehöhe und Fließzeit an der Stelle.
- **Kartenstile:** Satellit (Default, Luftbild DOP 2024 des LGV per WMS
  `config.DOP_WMS_URL`, dl-de/by-2.0; 2022 ist Pléiades mit geschlossener
  Lizenz und wird nicht genutzt), Höhen (Höhenstufen mit Schummerung), Atlas
  (hell, 1-m-Höhenlinien). Die Wahl merkt sich der Browser.
- **Rechnung im Browser** aus dem statischen Asset `web/public/overhaken.json`
  (2-m-Raster: Gelände, Überlaufhöhe, Klassen, Schummerung, Fließzeit in
  Minuten, Gebäude) wie `depth_at`: Wasserstand = Over-Messung, danach
  Overwerder-Vorhersage (cm über PNP → m NHN mit −5,098 m); Versickerung 10 cm/h;
  Fließzeit je Zelle wie oben.
- **Erzeugen** (eingecheckt, nur nach Änderung von Ausschnitt/Parametern nötig):

  ```bash
  uv run python inundation.py --recent --web-asset web/public/overhaken.json
  ```

  schreibt auch `web/public/overhaken_dop.jpg`. Zum lokalen Testen mit
  Sturmflut: `uv run python export_web.py --demo --demo-surge-cm 220 --out web/public`.

