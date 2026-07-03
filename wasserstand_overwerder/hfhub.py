"""Upload des Parquet-Archivs zu einem Hugging-Face-Dataset-Repo.

``huggingface_hub`` ist eine optionale Abhaengigkeit (Gruppe ``hf`` in
``pyproject.toml``) und wird erst beim Aufruf importiert. Authentifizierung ueber
das Argument ``token`` oder die Umgebungsvariable ``HF_TOKEN`` (bzw. einen zuvor
per ``huggingface-cli login`` hinterlegten Token).
"""

from __future__ import annotations

import os
from pathlib import Path

#: Default-Ziel: Dataset-Repo unter https://huggingface.co/aaronspring
DEFAULT_HF_REPO = "aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000"

# Dateien, die zusaetzlich zu den year=YYYY/-Partitionen ins Repo gehoeren.
_DATASET_CARD = "README.md"


def _upload_patterns(replace_years: list[int] | None) -> tuple[list[str], list[str]]:
    """(allow_patterns, delete_patterns) fuer upload_folder bestimmen.

    ``replace_years=None`` -> voller Spiegel: alle ``year=*``-Fragmente ersetzen.
    Sonst nur die genannten Jahres-Partitionen ersetzen, uebrige unberuehrt
    lassen (inkrementelles Update). ``delete_patterns`` entfernt die alten
    Fragmente im selben Commit, sodass keine Duplikate entstehen.
    """
    if replace_years is None:
        return ["year=*/*.parquet", _DATASET_CARD], ["year=*/*.parquet"]
    years = sorted(set(replace_years))
    allow = [f"year={y}/*.parquet" for y in years] + [_DATASET_CARD]
    delete = [f"year={y}/*.parquet" for y in years]
    return allow, delete


def dataset_card(repo_id: str, stations: list[str]) -> str:
    """Minimaler Dataset-Card-Text (YAML-Front-Matter + Beschreibung)."""
    station_list = ", ".join(stations)
    return f"""---
license: cc-by-4.0
language:
  - de
tags:
  - hydrology
  - tide
  - elbe
  - water-level
  - germany
pretty_name: Tideelbe-Pegel (minuetlich, cm ueber PNP)
configs:
  - config_name: default
    data_files: "year=*/*.parquet"
---

# Tideelbe-Pegel Overwerder (minuetliche Wasserstaende)

Minuetliche Rohdaten des Wasserstands **W in cm ueber PNP** fuer die
Tideelbe-Pegel **{station_list}**, seit 2000-01-01.

Quelle: PEGELONLINE-Langzeitarchiv der WSV
(<https://www.pegelonline.wsv.de>), "Download langfristiger Wasserstaende
(Rohdaten) ab dem 1.1.2000". Ungeprueft Rohdaten (koennen Ausreisser/Luecken
enthalten). Lizenz: DL-DE->Zero-2.0 / CC BY 4.0.

## Schema

| Spalte | Typ | Bedeutung |
|--------|-----|-----------|
| `time` | timestamp (UTC) | Messzeitpunkt, tz-aware UTC |
| `station` | string | Pegel-Schluessel ({station_list}) |
| `w_cm_pnp` | int | Wasserstand in cm ueber PNP |
| `year` | int | UTC-Jahr (Hive-Partition `year=YYYY/`) |

Partitionierung jaehrlich (`year=YYYY/`), Kompression zstd.

## Laden

```python
import pandas as pd

# einzelnes Jahr (laedt nur diese Partition)
df = pd.read_parquet("hf://datasets/{repo_id}/year=2015")

# gesamtes Archiv
df = pd.read_parquet("hf://datasets/{repo_id}")
```

Erzeugt mit
[`build_history.py`](https://github.com/aaronspring/wasserstandvorhersage_overwerder).
"""


def upload_dataset(
    local_dir: str | Path,
    repo_id: str = DEFAULT_HF_REPO,
    token: str | None = None,
    stations: list[str] | None = None,
    private: bool = False,
    commit_message: str = "Update Pegel-Archiv",
    replace_years: list[int] | None = None,
) -> str:
    """Lokales Parquet-Dataset zu einem HF-Dataset-Repo hochladen.

    Legt das Repo bei Bedarf an und schreibt eine Dataset-Card (README.md).
    ``replace_years=None`` spiegelt das gesamte Dataset (voller Backfill);
    eine Liste von Jahren ersetzt nur diese ``year=YYYY/``-Partitionen und
    laesst die uebrigen unangetastet (inkrementelles Update). Rueckgabe: URL.
    """
    from huggingface_hub import HfApi  # optionale Abhaengigkeit

    token = token or os.environ.get("HF_TOKEN")
    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)

    local = Path(local_dir)
    card = local / _DATASET_CARD
    card.write_text(
        dataset_card(repo_id, stations or ["over", "zollenspieker"]), encoding="utf-8"
    )

    allow, delete = _upload_patterns(replace_years)
    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(local),
        allow_patterns=allow,
        delete_patterns=delete,
        commit_message=commit_message,
    )
    return f"https://huggingface.co/datasets/{repo_id}"
