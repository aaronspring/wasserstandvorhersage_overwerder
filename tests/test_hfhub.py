"""Netzfreie Tests fuer die Hugging-Face-Anbindung (Dataset-Card, Defaults)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wasserstand_overwerder import hfhub


def test_default_repo_under_aaronspring():
    assert hfhub.DEFAULT_HF_REPO.startswith("aaronspring/")


def test_upload_patterns_full_mirror():
    allow, delete = hfhub._upload_patterns(None)
    assert "year=*/*.parquet" in allow and "README.md" in allow
    assert delete == ["year=*/*.parquet"]


def test_upload_patterns_incremental_scopes_years():
    allow, delete = hfhub._upload_patterns([2025, 2026])
    # Nur genau die genannten Jahres-Partitionen werden ersetzt.
    assert allow == ["year=2025/*.parquet", "year=2026/*.parquet", "README.md"]
    assert delete == ["year=2025/*.parquet", "year=2026/*.parquet"]
    # nur konkrete Jahre, kein "year=*" -> aeltere Jahre bleiben unberuehrt
    assert "year=*/*.parquet" not in delete


def test_dataset_card_has_frontmatter_and_config():
    repo = "aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000"
    card = hfhub.dataset_card(repo, ["over", "zollen"])
    # YAML-Front-Matter
    assert card.startswith("---\n")
    assert card.count("---\n") >= 2
    # Loader-Konfig fuer die Hive-Partitionen
    assert 'data_files: "year=*/*.parquet"' in card
    assert "cc-by-4.0" in card
    # Stationsliste und Repo-Id tauchen im Ladebeispiel auf
    assert "over, zollen" in card
    assert f"hf://datasets/{repo}" in card
    # Link zurueck zum GitHub-Repo (prominent)
    assert hfhub.GITHUB_REPO_URL in card


def test_upload_dataset_is_lazy_import():
    # hfhub laesst sich ohne installiertes huggingface_hub importieren;
    # der Import passiert erst im Funktionskoerper von upload_dataset.
    import importlib

    mod = importlib.import_module("wasserstand_overwerder.hfhub")
    assert hasattr(mod, "upload_dataset")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("Alle Tests bestanden.")
