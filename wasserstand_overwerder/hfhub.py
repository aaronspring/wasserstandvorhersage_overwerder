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
DEFAULT_HF_REPO = "aaronspring/tideelbe-pegel-minute"

# Dateien, die zusaetzlich zu den year=YYYY/-Partitionen ins Repo gehoeren.
_DATASET_CARD = "README.md"


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
) -> str:
    """Lokales Parquet-Dataset zu einem HF-Dataset-Repo hochladen.

    Legt das Repo bei Bedarf an, schreibt eine Dataset-Card (README.md) und
    spiegelt die ``year=YYYY/``-Partitionen. Rueckgabe: URL des Datasets.
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

    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(local),
        allow_patterns=["year=*/*.parquet", _DATASET_CARD],
        commit_message=commit_message,
    )
    return f"https://huggingface.co/datasets/{repo_id}"
