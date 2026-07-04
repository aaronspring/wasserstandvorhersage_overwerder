# Sturmfluten am Pegel Over — EDA: Häufigkeit, Saisonalität, Trend (2000–2026)

Explorative Auswertung aller **Tidehochwasser** am Pegel **Over** (Tideelbe,
Elbe-km 605,3, direkt gegenüber Overwerder) aus dem Langzeitarchiv. Sie
beantwortet drei Fragen:

1. **Saisonalität** — In welchem Monat sind Sturmfluten am wahrscheinlichsten?
2. **Häufigkeit** — Wie viele Sturmfluten pro Saison, welche Klassen?
3. **Trend** — Werden Sturmfluten über die Jahre **häufiger** oder **stärker**?

Reproduzierbar mit `analyse_sturmfluten.py` (Kennzahlen + Figuren); die Logik
steht netzfrei/testbar in `wasserstand_overwerder/sturmflut.py`
(`tests/test_sturmflut.py`).

## Kurzantwort

- **Saisonalität:** Sturmfluten sind ein reines **Winterphänomen**. **95 %**
  aller Sturmflut-Tiden fallen in **Okt–Mär**, fast 78 % allein in **Nov–Feb**.
  Zwischen **Mai und September** trat 2000–2026 praktisch keine Sturmflut auf.
- **Häufigkeit:** im Mittel **6,2 Sturmflut-Tiden pro Saison** (Jul–Jun), aber
  mit enormer Streuung — von **0** (Saison 2008/09) bis **19** (2021/22).
- **Stärker/häufiger über die Zeit?** **Kein statistisch belastbarer Trend**
  weder in der Häufigkeit (+0,7/Dekade, p = 0,59) noch in der Intensität
  (+8 cm/Dekade beim Saison-Höchstscheitel, p = 0,64). Die Jahr-zu-Jahr-
  Schwankung (Großwetterlage/NAO) dominiert das 26-Jahres-Fenster. Das
  **einzige** signifikante Langzeitsignal ist ein **langsamer Anstieg des
  mittleren Tidehochwassers (MThw) um ≈ 4 cm/Dekade** (p ≈ 0,03) — die *Basis*,
  von der jede Sturmflut startet, steigt, die *Sturmintensität* selbst nicht
  nachweisbar.

> **26 Jahre sind kurz** für Aussagen über das Sturmklima. Alle Trends sind mit
> dieser Einschränkung zu lesen; die Vorbehalte stehen unten.

## Was ist eine (schwere) Sturmflut? — BSH-Definition

Das **BSH** klassifiziert Sturmfluten an der **Nordseeküste** über den Aufschlag
des Scheitels auf das **mittlere Tidehochwasser (MThw)** des jeweiligen Pegels:

| Klasse | Scheitel über MThw | am Pegel Over (MThw ≈ 746 cm ü. PNP) |
|---|---|---|
| **Sturmflut** (leicht/mittel) | 1,5 – 2,5 m | ≥ **896** cm ü. PNP |
| **schwere Sturmflut** | 2,5 – 3,5 m | ≥ **996** cm ü. PNP |
| **sehr schwere Sturmflut** | > 3,5 m | ≥ **1096** cm ü. PNP |

Unter MThw + 1,5 m spricht das BSH nicht von einer Sturmflut. (Quelle:
BSH-Sturmflut-Klassifikation Nordsee; an der Ostsee gelten andere, niedrigere
Schwellen.)

**Wichtiger Vorbehalt zum Bezug:** Die offizielle Klassifikation bezieht sich in
Hamburg auf den Pegel **Hamburg St. Pauli** und dessen MThw. St. Pauli ist
**nicht** im Langzeitarchiv (HPA-Pegel, siehe `CLAUDE.md`). Diese Auswertung
verwendet daher das **aus den Over-Daten selbst geschätzte MThw** (Mittel aller
Tidehochwasser 2000–2026 = **746 cm ü. PNP = +2,46 m NHN**) als Bezug. Die
absoluten Klassengrenzen liegen dadurch etwas anders als offizielle
St.-Pauli-Werte; die Ereignis-*Reihenfolge* und die *relativen* Aussagen
(Saisonalität, Trend) bleiben davon unberührt.

## 1) Saisonalität

![Saisonalität der Sturmfluten](sturmflut_saisonalitaet.png)

Verteilung der 163 Sturmflut-Tiden auf die Monate (gestapelt nach Klasse):

| Monat | Tiden | Anteil |
|---|---:|---:|
| Dezember | 28 | 17 % |
| Januar | 48 | 29 % |
| Februar | 32 | 20 % |
| November | 19 | 12 % |
| Oktober | 14 | 9 % |
| März | 14 | 9 % |
| Apr–Sep | 8 | 5 % |

**Höchste Sturmflut-Wahrscheinlichkeit im Kernwinter (Dez–Feb)**; die
Übergangsmonate Okt/Nov und Mär tragen den Rest. Die wenigen Sommertreffer
(Jun–Sep, je 1–2) sind Grenzfälle knapp über der Schwelle. Auch alle
**schweren/sehr schweren** Sturmfluten liegen ausnahmslos im Winterhalbjahr.

## 2) Häufigkeit je Saison

![Häufigkeit je Saison](sturmflut_haeufigkeit.png)

Gezählt werden **Sturmflut-Tiden je Sturmflut-Saison** (Jul–Jun, benannt nach
dem Startjahr) — jede Tide über der Schwelle zählt, wie in der BSH/HPA-Statistik
üblich (ein Sturm kann mehrere Sturmflut-Tiden erzeugen).

- Mittel **6,2 Tiden/Saison**, Median 5, Spanne **0 … 19**.
- Rekordsaison **2021/22** mit **19** Sturmflut-Tiden (u. a. Zeynep/Antonia,
  Nadia); dagegen **2008/09** ohne eine einzige.
- Diese hohe Streuung — nicht ein Trend — prägt das Bild.

**Klassenverteilung gesamt (2000–2026):**

| Klasse | Tiden |
|---|---:|
| Sturmflut | 143 |
| schwere Sturmflut | 18 |
| sehr schwere Sturmflut | 2 |

Die zwei **sehr schweren** Sturmfluten sind die Rekorde **Xaver** (06.12.2013,
1114 cm) und **Zeynep/Antonia** (19.02.2022, 1110 cm) — deckungsgleich mit den
[Top-10-Sturmfluten](TOP_10_STURMFLUTEN.md).

## 3) Trend: häufiger oder stärker?

![Intensität jeder Sturmflut-Tide](sturmflut_intensitaet.png)

**Häufigkeit:** lineare Regression der Tiden/Saison ergibt +0,7/Dekade, ist aber
statistisch **nicht signifikant** (r = 0,11, p = 0,59; Mann-Kendall p ≈ 0,67).
Erste vs. zweite Hälfte: 5,9 → 6,5 Tiden/Saison — ein leichter, aber im Rauschen
untergehender Anstieg.

**Intensität:** der Trend des Saison-Höchstscheitels beträgt +8 cm/Dekade,
ebenfalls **nicht signifikant** (r = 0,10, p = 0,64); die mittlere Scheitelhöhe
je Tide ist praktisch flach. Bei den **schweren+ Sturmfluten** fällt aber auf,
dass die zweite Zeithälfte mehr davon enthält (**13** gegenüber **6**) — ein
Hinweis, aber bei so kleinen Zahlen kein Beleg.

![MThw-Drift](sturmflut_mthw_drift.png)

**Das einzige belastbare Signal — der Hintergrundpegel steigt.** Das jährliche
MThw (Mittel *aller* Tidehochwasser) steigt um **≈ 4 cm/Dekade** und ist als
einziges der geprüften Maße **signifikant** (r = 0,41, p ≈ 0,03). Das passt zu
Meeresspiegelanstieg und der bekannten Tideverstärkung in der Elbe. Konsequenz:
Bei *fester* Schwelle nimmt die Zahl der Überschreitungen allein deshalb zu, weil
die Basis steigt — nicht weil die Stürme heftiger werden. Für das reale
Überflutungsrisiko in Overwerder zählt genau diese Summe (höhere Basis + gleiche
Sturmintensität = höhere absolute Scheitel).

## Methodik

1. **Laden & Normieren:** Pegel Over aus dem HF-Dataset
   `aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000`, minütlich,
   cm über PNP, Zeit tz-aware UTC. Plausibilitätsfilter `PLAUSIBLE_CM_PNP`
   (50–1300 cm) gegen Roh-Ausreißer.
2. **Tidehochwasser (Thw):** 11-min-Median gegen Ein-Minuten-Spikes (wie in der
   Top-10-Methodik), dann lokale Maxima mit Mindestabstand 600 min (< die
   ~745 min zwischen zwei Halbtags-Tiden). Ergebnis: **18 695 Thw**, mittlerer
   Abstand 12,4 h — konsistent mit dem halbtägigen Tideregime.
3. **MThw** = Mittel aller Thw = 746 cm ü. PNP (Bezug für die Klassen).
4. **Klassifikation** nach BSH-Nordsee-Schwellen (MThw + 1,5 / 2,5 / 3,5 m).
5. **Aggregation:** Saison = Jul–Jun (Startjahr); Trends per linearer Regression
   (Steigung, r, zweiseitiger p-Wert). Nur vollständig abgedeckte Saisons
   2000/01 … 2024/25 fließen in die Trends ein (Reihe endet Juli 2026).

### Reproduktion

```bash
uv sync --extra hf
uv run python analyse_sturmfluten.py            # Kennzahlen + docs/sturmflut_*.png
uv run python analyse_sturmfluten.py --no-figures
# offline auf lokaler Parquet-Datei (Spalten time, w_cm_pnp):
uv run python analyse_sturmfluten.py --data pfad/zu/over.parquet
```

## Vorbehalte

- **Kurzes Fenster (26 Jahre).** Sturmklima-Trends brauchen längere Reihen; die
  hier gefundene Nicht-Signifikanz heißt „im Rauschen nicht nachweisbar", nicht
  „sicher kein Trend". Die interannuelle Variabilität (NAO/Großwetterlage) ist
  groß.
- **Bezug MThw des Pegels Over**, nicht St. Pauli (HPA-Pegel fehlt im Archiv).
  Absolute Klassengrenzen weichen daher von offiziellen St.-Pauli-Werten ab.
- **MThw als voller-Zeitraum-Mittel** ist selbst nicht stationär (es steigt, s.
  o.). Ein festes MThw über 2000–2026 ist eine pragmatische Wahl; ein
  gleitendes MThw würde den Basis-Anstieg aus den Sturmflut-Zahlen
  herausrechnen — bewusst nicht getan, da die absolute Scheitelhöhe das
  Überflutungsrisiko bestimmt.
- **Ungeprüfte Rohdaten**, heuristische Thw-Erkennung. Grenzfälle knapp an der
  Schwelle können einzelne Zählungen leicht verschieben; die qualitativen
  Aussagen (starke Winter-Saisonalität, kein Intensitätstrend, MThw-Anstieg)
  sind robust. Modell-Vorbehalt zu Sturmfluten: [`CAVEAT.md`](CAVEAT.md).
