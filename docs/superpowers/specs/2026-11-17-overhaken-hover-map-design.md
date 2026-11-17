# Overhaken-Karte zum Hover-Zeitpunkt (Web-App) - Design

## Intent
Wer im Wasserstands-Chart mit der Maus ueber einen Zeitpunkt faehrt (oder ihn
antippt), sieht daneben eine Karte der Kolonie Overhaken (Huetten 101-141, Elbe
im Westen) mit dem Wasser zu genau diesem Zeitpunkt. Ohne Hover: "jetzt".
Kein Slider.

## Approaches
1. **Karte neben/unter dem Chart, per Hover gekoppelt** - gewaehlt. Zeigt, woher
   das Wasser kommt (Elbe, Priel) und welche Huetten es erreicht.
2. Mini-Karte im Tooltip - zu klein, verdeckt den Chart.
3. Huetten-Leiste ohne Gelaende - kompakt, aber ohne Raumbezug; braucht die
   Parzellenliste des Vereins.

## Design
- **Statisches Asset** `web/public/overhaken.json` (eingecheckt, Gelaende aendert
  sich nicht): 2-m-Raster des Kartenausschnitts `config.INUNDATION_VIEW` mit
  Gelaende `z`, Ueberlaufhoehe `spill` (beide cm NHN, Int16, base64),
  Klassen (Land / Elbe / sonstiges Wasser), Schummerung (Uint8), Gebaeude
  (Grundriss, `nr`, `base_m`, `spill_m`, Adresse), Over-PNP (-5,098 m NHN).
  Erzeugt von `inundation.py --web-asset ...` (netzfreie Funktion
  `inundation_web.build_asset`, getestet).
- **Rechnung im Browser** (wie `inundation.depth_at`, Versickerung 10 cm/h): Wasserstand
  L(t) aus Over-Messung, danach Overwerder-Vorhersage; laufendes Maximum R(t).
  Zelle nass, wenn `spill <= R`; Spiegel `max(L, spill - v * h)` mit
  Versickerung v und h = Stunden seit dem letzten Kontakt zum Strom (Stauwasser
  in Senken versickert), Tiefe = Spiegel - z.
- **Kopplung:** kleiner Store `cursor.ts`; der Chart meldet Hover-Zeit und
  fixierte Ablese-Linie, die Karte liest `hover ?? pinned ?? jetzt`. Die App
  rendert dadurch nicht bei jeder Mausbewegung neu.
- **Anzeige:** Canvas (Schummerung, Elbe, Tiefe in Blaustufen) + SVG (Gebaeude,
  eingefaerbt nach Tiefe am Gebaeude; Titel mit Nr., Bodenhoehe, "nass ab").
  Kopfzeile: Zeitpunkt, Messung/Vorhersage, Over-Stand.
- **Lokal pruefen:** `export_web.py --demo --demo-surge-cm 220` erzeugt eine
  Sturmflut in den Demo-Daten.

## Non-goals
Keine Abflussphysik (Badewanne mit Verbindung, Beginn = fruehestmoeglich), keine
echten Huettennummern (laufende `nr`), kein Slider, keine Animation.
