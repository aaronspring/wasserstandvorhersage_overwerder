# Vorbehalte: Sturmfluten und Grenzen des Interpolationsmodells

*Dieses Dokument erklärt, warum das Interpolationsmodell bei normalen Tiden gut,
bei Sturmfluten aber nur eingeschränkt gültig ist.*

## Inhaltsverzeichnis

- [Beobachteter Zusammenhang Zollenspieker ↔ Over (Normaltiden)](#beobachteter-zusammenhang-zollenspieker--over-normaltiden)
- [Sturmfluten: Warum das Modell hier unsicher ist](#sturmfluten-warum-das-modell-hier-unsicher-ist)
- [Konsequenz für die Nutzung](#konsequenz-für-die-nutzung)

Dieses Dokument hält fest, wie sich der Zusammenhang zwischen den Stützpegeln
und dem Zielort Overwerder bei **normalen Tiden** verhält und warum das Modell
bei **Sturmfluten** nur eingeschränkt gültig ist. Einheiten: cm über PNP
(PNP = NHN − 5,00 m), Zeiten UTC.

## Beobachteter Zusammenhang Zollenspieker ↔ Over (Normaltiden)

Empirisch aus 30 Tagen PEGELONLINE-Messung (Juni/Juli 2026, beide Serien auf
ein gemeinsames 1-min-Raster interpoliert, Korrelation r ≈ 0,98):

| Größe | Zollenspieker (km 598,3) | Over (km 605,3) |
| --- | --- | --- |
| Median | 578 cm | 572 cm |
| Hochwasser (P95) | 751 cm | 747 cm |
| Niedrigwasser (P5) | 420 cm | 398 cm |
| Tidenhub (P95−P5) | 331 cm | 349 cm |

- **Amplitude:** Over schwingt insgesamt ~5 % weiter (Hubverhältnis ≈ 1,05).
  Der Mehr-Hub kommt fast vollständig vom **tieferen Niedrigwasser**; am
  **Hochwasser** sind beide praktisch gleich (Zollenspieker sogar ~5 cm höher).
- **Phase:** Over eilt Zollenspieker um **~30 min voraus**
  (Vollsignal-Kreuzkorrelation; am flachen HW-Scheitel selbst nur ~15–19 min).
  Physikalisch korrekt: die Tidewelle läuft **stromauf**, Elbe-km wächst
  stromab; Over liegt stromab von Zollenspieker und sieht die Welle früher.
  Die ~7 km entsprechen einer Laufzeit von ~30 min (≈ 4,3 min/km), konsistent
  mit dem kalibrierten τ ≈ 50 min über die volle Strecke St. Pauli↔Zollenspieker.

Diese Kennzahlen stützen die Modellannahme einer zeitversetzt-gewichteten
Interpolation für den Normalbetrieb.

## Sturmfluten: Warum das Modell hier unsicher ist

**Der übliche PEGELONLINE-Zeitraum (max. 31 Tage) enthält oft keine
Sturmflut.** Im o. g. Fenster lag das höchste HW bei Over ≈ 834 cm PNP — unter
der Schwelle einer *leichten* Sturmflut. Der Sturmflut-Fall lässt sich damit
**nicht direkt kalibrieren oder verifizieren.**

Sturmflut-Schwellen (bezogen auf St.-Pauli-MThw ≈ 2,10 m NHN = 710 cm PNP,
Definition HPA/BSH):

| Kategorie | über MThw | ≈ cm PNP (St. Pauli) |
| --- | --- | --- |
| leichte Sturmflut | +1,5 … 2,5 m | ≥ 860 |
| schwere Sturmflut | +2,5 … 3,5 m | ≥ 960 |
| sehr schwere Sturmflut | > 3,5 m | ≥ 1060 |

Eine Sturmflut ist eine extern erzwungene **lange Welle** (Nordsee-Fernwelle +
Windstau), die der astronomischen Tide überlagert wird. Ihre Wellenlänge ist
Hunderte km — über die ~7 km Zollenspieker↔Over ist der Stauanteil praktisch
**phasengleich**. Daraus folgt:

1. **Amplitudenverhältnis → gegen 1.** Der Sturmstau hebt beide Pegel um fast
   denselben Betrag; das +5-%-Muster aus dem Tidenhub verwässert. Bei sehr
   schweren Fluten kann durch **Windstau + Oberwasser (Oberelbe-Abfluss) +
   Trichter-/Reflexionseffekte** der HW-Gradient sogar kippen: Zollenspieker
   (stromauf) erreicht dann so hohe oder höhere HW-Scheitel als Over. Der schon
   bei Normaltiden sichtbare Befund „Zollenspieker-HW ≈ / etwas höher"
   verstärkt sich.
2. **Phasenverschiebung → kleiner.** Der Scheitelzeitpunkt wird vom Stau
   bestimmt, nicht von der astronomischen Laufzeit. Die ~30 min Tidenlag
   beschreiben den echten Sturmflut-Scheitel **nicht mehr**; die effektive
   Verschiebung schrumpft Richtung 0.
3. **Niedrigwasser komprimiert.** Bei auflandigem Sturm wird das NW
   „festgehalten"; der Mehr-Hub von Over (der vom NW kommt) verschwindet
   weitgehend.

Auch in den Normaltiden-Daten deutet sich der Trend an: je höher das HW, desto
größer der Vorsprung von Over (−15 → −19 min am Scheitel; r ≈ −0,34) bei
weiterhin ~5 cm niedrigerem Over-HW gegenüber Zollenspieker.

## Konsequenz für die Nutzung

- Das lineare Modell (**konstantes τ, feste Gewichte, fester Offset**, kalibriert
  auf Normaltiden) ist bei Sturmfluten **am unsichersten**.
- Im Sturmflut-Regime (Richtwert HW ≥ ~860 cm PNP) ist die maßgebliche Quelle
  die **BSH-Kurvenvorhersage selbst**, die den Sturmstau für Zollenspieker und
  St. Pauli explizit modelliert. Die Interpolation auf Overwerder trägt dort
  die größte Restunsicherheit.
- Ein separates **Hochwasser-Regime** (eigene τ/Gewichte) ließe sich erst
  sinnvoll kalibrieren, sobald ein Sturmflut-Zeitraum in den Messdaten liegt.
