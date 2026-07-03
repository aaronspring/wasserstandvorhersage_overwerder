# Top 10 Sturmfluten am Pegel Over (2000–2026)

Auswertung der zehn höchsten Sturmflut-Scheitel am **Pegel Over** (Elbe-km 605,3,
direkt gegenüber Overwerder) aus dem Langzeitarchiv. Einheiten: cm über PNP
(PNP = NHN − 5,00 m); Scheitelzeitpunkte in gesetzlicher Zeit (MEZ/MESZ).

## Ergebnis

| #  | Scheitel (Europe/Berlin) | cm ü. PNP | m NHN  | Sturm |
|----|--------------------------|-----------|--------|-------|
| 1  | 2013-12-06 06:31         | 1114      | +6,14  | [Xaver](https://de.wikipedia.org/wiki/Orkan_Xaver) |
| 2  | 2022-02-19 05:41         | 1110      | +6,10  | [Zeynep](https://de.wikipedia.org/wiki/Orkan_Zeynep)/Antonia |
| 3  | 2007-11-09 15:51         | 1067      | +5,67  | [Tilo](https://de.wikipedia.org/wiki/Orkan_Tilo) |
| 4  | 2017-10-29 09:38         | 1064      | +5,64  | [Herwart](https://de.wikipedia.org/wiki/Sturmtief_Herwart) |
| 5  | 2023-12-22 11:05         | 1060      | +5,60  | Dezember 2023 (Zoltan/Pia) |
| 6  | 2002-01-29 04:01         | 1050      | +5,50  | Januar 2002 |
| 7  | 2000-01-30 09:54         | 1033      | +5,33  | Januar 2000 |
| 8  | 2015-01-11 07:25         | 1030      | +5,30  | Felix/Elon |
| 9  | 2022-01-30 00:49         | 1021      | +5,21  | [Nadia](https://de.wikipedia.org/wiki/Sturmtief_Nadia) |
| 10 | 2008-03-01 19:50         | 1008      | +5,08  | [Emma](https://de.wikipedia.org/wiki/Orkan_Emma) |

Die beiden Rekord-Sturmfluten **Xaver** (Dezember 2013) und **Zeynep/Antonia**
(Februar 2022) liegen mit rund 11,1 m über PNP klar an der Spitze — das deckt
sich mit den dokumentierten Rekordwasserständen der Tideelbe.

Sturmnamen sind, wo ein Artikel existiert, mit der deutschen Wikipedia verlinkt.
Für die Ereignisse ohne eigenständigen Artikel (Dezember 2023 / Zoltan-Pia,
Januar 2002, Januar 2000, Elon/Felix Januar 2015) ist nur das Datum angegeben.

## Datengrundlage

- **Quelle:** Hugging-Face-Dataset
  [`aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000`](https://huggingface.co/datasets/aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000),
  gespeist aus dem PEGELONLINE-Langzeitarchiv der WSV („Download langfristiger
  Wasserstände (Rohdaten) ab dem 1.1.2000").
- **Pegel:** Over (`station == "over"`), minütliche Rohdaten, W in cm über PNP.
- **Zeitraum:** 2000-01-01 bis zum aktuellsten Archivstand (hier bis Juli 2026).
- Es werden ausschließlich die im Dataset enthaltenen Pegel Over und
  Zollenspieker verwendet; der HPA-Pegel Hamburg St. Pauli ist nicht im
  Langzeitarchiv (siehe `AGENTS.md`/`CLAUDE.md`).

## Methodik

1. **Laden & Normieren:** Alle `year=YYYY/`-Partitionen des Pegels Over werden
   geladen; Zeitindex tz-aware UTC, Werte cm über PNP.
2. **Plausibilitätsfilter:** Werte außerhalb von `PLAUSIBLE_CM_PNP`
   (50–1300 cm über PNP) werden als Ausreißer verworfen (das Archiv enthält
   ungeprüfte Rohdaten).
3. **Spike-Glättung:** Rollierender Median über ein 11-Minuten-Fenster
   (`center=True`) entfernt einzelne Ein-Minuten-Ausschläge, ohne den
   Tidescheitel zu verschieben.
4. **Kandidaten:** Minuten oberhalb des 99,9-%-Perzentils der geglätteten
   Reihe (hier ≈ 911 cm über PNP) gelten als Sturmflut-Kandidaten.
5. **Ereignis-Clustering:** Kandidatminuten, die weniger als **36 h**
   auseinanderliegen, gehören zum selben Sturmereignis; je Ereignis wird nur
   der höchste Scheitel behalten. So zählen die mehreren Tidehochwasser
   während eines Sturms nicht mehrfach.
6. **Ranking:** Die Ereignisse werden nach Scheitelwasserstand sortiert; die
   Top 10 werden ausgegeben. Umrechnung `m NHN = cm PNP / 100 − 5,00`.

### Reproduktion

```python
import pandas as pd
import pyarrow.dataset as ds
from huggingface_hub import HfFileSystem

from wasserstand_overwerder.config import PEGELONLINE_HF_REPO, PLAUSIBLE_CM_PNP

LO, HI = PLAUSIBLE_CM_PNP
EVENT_GAP = pd.Timedelta("36h")

fs = HfFileSystem()
files = fs.glob(f"datasets/{PEGELONLINE_HF_REPO}/year=*/*.parquet")
dataset = ds.dataset(files, filesystem=fs, format="parquet")
tbl = dataset.to_table(
    columns=["time", "station", "w_cm_pnp"],
    filter=ds.field("station") == "over",
)
df = tbl.to_pandas().sort_values("time")
df = df[(df["w_cm_pnp"] >= LO) & (df["w_cm_pnp"] <= HI)]

s = pd.Series(df["w_cm_pnp"].to_numpy(), index=pd.DatetimeIndex(df["time"]))
s_sm = s.rolling("11min", center=True).median()
cand = s_sm[s_sm >= s_sm.quantile(0.999)].dropna()

events, cur_t, cur_v, last_t = [], None, None, None
for t, v in cand.items():
    if last_t is None or (t - last_t) > EVENT_GAP:
        if cur_t is not None:
            events.append((cur_t, cur_v))
        cur_t, cur_v = t, v
    elif v > cur_v:
        cur_t, cur_v = t, v
    last_t = t
if cur_t is not None:
    events.append((cur_t, cur_v))

ev = pd.DataFrame(events, columns=["peak_time_utc", "peak_cm_pnp"])
ev = ev.sort_values("peak_cm_pnp", ascending=False).head(10).reset_index(drop=True)
ev["peak_time_berlin"] = ev["peak_time_utc"].dt.tz_convert("Europe/Berlin")
ev["peak_m_nhn"] = ev["peak_cm_pnp"] / 100.0 - 5.0
print(ev)
```

Benötigt das optionale Extra `hf` (`uv sync --extra hf`) für `huggingface_hub`.

## Vorbehalte

- **Ranking rein nach Scheitelwasserstand am Pegel Over.** Die offizielle
  Sturmflut-Klassifikation der HPA/des BSH bezieht sich auf den Pegel Hamburg
  St. Pauli und dessen mittleres Tidehochwasser (MThw); dieser Pegel ist nicht
  Teil des Datensatzes.
- **Ungeprüfte Rohdaten.** Reihenfolge und Absolutwerte der eng
  beieinanderliegenden Ereignisse (Plätze 5–10, Abstände von wenigen cm)
  können sich mit geprüften Daten leicht verschieben.
- **Ereignisdefinition ist heuristisch.** Das 36-h-Clusterfenster und die
  99,9-%-Schwelle sind pragmatisch gewählt; andere Parameter können einzelne
  Grenzfälle anders zuordnen. Der Modell-Vorbehalt zu Sturmfluten steht in
  [`CAVEAT.md`](CAVEAT.md).
