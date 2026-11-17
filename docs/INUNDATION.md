# Overhaken-Karte: Wasser auf dem Gelände zum gewählten Zeitpunkt (DGM1)

Neben dem Wasserstands-Chart zeigt die Web-App eine Karte der Kolonie
Overhaken (Freizeit-, Sport- und Gartenverein Overhaken e. V., Hütten 101–141,
Elbe im Westen). Für jeden Zeitpunkt der Messung oder Vorhersage zeigt sie,
**wo** und **wie tief** Wasser steht. Gerechnet wird im Browser aus einem
statischen Gelände-Asset, das `inundation.py` einmal erzeugt.

## Daten

| | |
|---|---|
| Gelände | **DGM1 2022**, LGV Hamburg (Laserscanning, 1 m, EPSG:25832, m ü. NHN/DHHN2016, ±15 cm) |
| Bezug | Transparenzportal „Geländemodelle Hamburg – DGM“; ZIP (1,3 GB) auf `archiv.transparenz.hamburg.de`, die alten `daten-hamburg.de`-Links liefern 404 |
| Download | per HTTP-Range nur die 1-km-Kacheln des Ausschnitts (`remotezip`), Cache `out/dgm1/`; im ZIP fehlende Kacheln stehen in `out/dgm1/absent.txt` |
| Gebäude | **LoD2-DE 2026**, LGV Hamburg (CityGML-Kacheln, Grundriss aus ALKIS, Bodenhöhe, Hausnummer falls vergeben), Cache `out/lod2/` |
| Luftbild | **DOP 2024** (belaubt), LGV-WMS `wms_dop_zeitreihe_belaubt`; 2022 ist Pléiades mit geschlossener Lizenz und wird nicht genutzt |
| Lizenz | Datenlizenz Deutschland – Namensnennung 2.0, © LGV Hamburg |
| Wasserstand | Pegel Over (Messung) und Overwerder-Vorhersage aus `data.json`, cm über PNP → m NHN mit **PNP = −5,098 m NHN** (PEGELONLINE `gaugeZero`, nicht −5,00) |

## Auflösung

| | räumlich | Höhe / Wert | Genauigkeit |
|---|---|---|---|
| Gelände DGM1 | gerechnet in 1 m (Überlaufhöhe, 5,5 Mio. Zellen), Karte in 2 m | 1-cm-Schritte | ±15 cm auf eindeutigen Flächen (Straßen), schlechter unter dichter Vegetation und an Böschungen |
| Wasserstand | ein Punkt (Over, km 605,3), gilt für das ganze Vorland | 1 cm | Zeitschritt der Reihe (10 min) |
| Gebäude LoD2 | Grundriss aus dem Kataster (cm-genau) | Bodenhöhe aus dem DGM | ALKIS-Stand je Gebäude |

Was das für den Zeitpunkt heißt: ±15 cm Höhe entsprechen auf dem steigenden
Ast etwa ±10 min, nahe dem Scheitel eher ±15–25 min. Faustregel: 10 cm mehr
Gelände bedeuten rund 6–8 min späteren Beginn. Strukturen schmaler als ~2 m
(Zäune, Mauern, schmale Gräben) sind nur unscharf oder gar nicht abgebildet.

Fallstricke im DGM1:

* Wasserflächen sind mit glatten Platzhaltern gefüllt (Elbe **2,00 m**,
  Hohendeicher See **1,00 m**). Ungefiltert wirkt die Elbe als künstliche
  2-m-Schwelle. `water_fill_mask` setzt sie auf NaN.
* Das niedersächsische Ufer fehlt (NaN). Die größte NaN-Fläche ist der Strom
  und damit die Wasserquelle.
* Das Flussbett und der Elbstrand unterhalb der Wasserlinie bei der Befliegung
  fehlen. Wie viel Strand bei Niedrigwasser trockenfällt, lässt sich daraus
  nicht ablesen (dafür bräuchte es ein DGM-W der WSV).

## Methode

1. **Überlaufhöhe** je Zelle (`inundation.spill_elevation`, Python): Das ist
   der niedrigste Elbe-Wasserstand, bei dem die Zelle über einen
   zusammenhängenden Weg nass wird (Minimax-Pfad, morphologische
   Rekonstruktion durch Erosion, 8er-Nachbarschaft). Senken hinter einem
   Sommerdeich laufen also erst bei dessen Überströmung voll. Das Hinterland
   hinter dem Hauptdeich (Krone ≥ 8 m NHN) bleibt trocken. Gerechnet wird auf
   dem großen Modellausschnitt `INUNDATION_BBOX`, damit die Wasserwege stimmen.
2. **Fließweg** je Zelle (`inundation.travel_distance`, Python): der kürzeste
   Weg vom Strom über Zellen, die zu dem Zeitpunkt schon nass sind. Eine Zelle
   mit Überlaufhöhe *s* wird nur über Zellen mit Überlaufhöhe ≤ *s* erreicht
   (0,1-m-Stufen, 8er-Nachbarschaft, Weg im Strom zählt nicht). Geteilt durch
   v = 0,3 m/s (`config.INUNDATION_FLOW_M_S`) ergibt das die **Fließzeit**.
3. **Wasser zum Zeitpunkt *T*** (im Browser, `web/src/OverhakenMap.tsx`): Eine
   Zelle mit Fließzeit *t* sieht den Wasserstand von *T − t*.
   * **Auflauf:** Die Zelle ist nass, sobald das laufende Maximum des
     Wasserstands ihre Überlaufhöhe erreicht hat.
   * **Ablauf:** Fällt der Strom, sinkt der Spiegel einer Zelle nur bis auf ihre
     Überlaufhöhe. Was über Priele mit dem Strom verbunden ist, läuft mit der
     Tide ab. Abflusslose Mulden behalten **Stauwasser**, das mit 10 cm/h
     versickert (`config.INUNDATION_DRAIN_M_PER_H`, Sandboden, angenommen).
     Unter den Außenwasserstand sinkt es nicht.
   * **Formel:** Spiegel = max(Wasserstand, Überlaufhöhe − Versickerung ·
     Stunden seit dem letzten Kontakt zum Strom), Tiefe = Spiegel − Gelände.

**Warum 0,3 m/s:** Gemeint ist flaches Überströmen von Wiese und Parzellen. Nach
Manning *v = h^(2/3) · S^(1/2) / n* mit Wassertiefe h ≈ 0,3 m, Gefälle
S ≈ 1 ‰ und Rauheit n ≈ 0,05 (Gras, Büsche, Zäune) ergibt sich v ≈ 0,28 m/s.
Die übliche Spanne ist 0,1–0,5 m/s, in Prielen bis ~1 m/s. Die Tidewelle in
der Elbe selbst (~5–7 m/s) steckt schon im Pegel Over. Im Kartenausschnitt
liegt die Fließzeit im Median bei 6 min, bei 90 % der Fläche unter 20 min,
höchstens bei 32 min. Da die Tide vor dem Scheitel um 30–70 cm/h steigt,
verschiebt das den Beginn nur leicht.

**Grenzen:**
* Es ist ein Badewannenmodell mit Verbindung und konstanter Fließgeschwindigkeit,
  ohne Durchflussmengen: Ein schmaler Durchlass füllt eine große Senke in
  Wirklichkeit langsamer. Dafür bräuchte es ein 2D-Modell (z. B. LISFLOOD-FP).
* Die Versickerungsrate ist angenommen.
* Die Wasserspiegellage von Over gilt für das ganze Vorland (Over liegt
  gegenüber, km 605,3).
* Zäune, Lauben und Sandsäcke sind nicht im DGM enthalten.

## Gebäude

`buildings.py` lädt die LoD2-Kacheln und nimmt die **53 Gebäude** in
`OVERHAKEN_BBOX` mit Überlaufhöhe < 7 m (Vorland). Das sind mehr als die
41 Hütten, weil LoD2 auch Schuppen zählt; dazu kommt Overwerder Bogen 78.
Hausnummern gibt es kaum, die Lauben haben in ALKIS keine. Jedes Gebäude
bekommt deshalb eine **laufende Nummer** (`nr`, entlang des Deichs von NW nach
SO). Die ALKIS-Kennung (`alkis_id`) bleibt für den Abgleich mit einer
Parzellenliste des Vereins erhalten. Je Gebäude stehen Bodenhöhe `base_m` und
Überlaufhöhe `spill_m` (niedrigste im Grundriss) im Asset. Die Karte färbt es
nach der Wassertiefe über der Bodenhöhe ein.

## Web-Karte

- **Zeitpunkt:** Hover im Chart; ein Klick fixiert ihn („fixiert“), der nächste
  Klick löst ihn wieder; ohne beides „jetzt“. Auf Touch-Geräten setzt nur das
  Tippen (fixieren) den Zeitpunkt.
- **Hover auf der Karte:** Wassertiefe, Geländehöhe und Fließzeit an der Stelle.
- **Kartenstile:** Satellit (Default, Luftbild 2024), Höhen (Höhenstufen mit
  Schummerung), Atlas (hell, 1-m-Höhenlinien). Die Wahl merkt sich der Browser.
  Fehlt das Luftbild im Asset, zeigt die Karte „Höhen“.
- **Asset** `web/public/overhaken.json` (2-m-Raster des Ausschnitts
  `INUNDATION_VIEW`: Gelände, Überlaufhöhe, Klassen Land/Elbe/sonstiges Wasser,
  Schummerung, Fließzeit in Minuten; Gebäude, Beschriftungen, PNP,
  Versickerung) und `web/public/overhaken_dop.jpg`. Beide sind eingecheckt, der
  Deploy braucht kein Python dafür.

## Asset erzeugen

Nur nötig, wenn sich Ausschnitt oder Parameter in `config.py` ändern
(`INUNDATION_*`, `OVERHAKEN_BBOX`, `DOP_*`):

```bash
uv sync --extra gelaende
uv run python inundation.py            # ~35 s, erster Lauf lädt ~35 MB Kacheln
uv run python inundation.py --no-photo # ohne Luftbild-Download
```

Zum lokalen Testen mit Sturmflut:

```bash
uv run python export_web.py --demo --demo-surge-cm 220 --out web/public
cd web && npm run dev
```
