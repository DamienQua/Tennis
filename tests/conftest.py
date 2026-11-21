"""Configuration pytest et ajout de la racine du projet au PYTHONPATH."""

import os
import sys
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


@pytest.fixture(autouse=True)
def isolated_working_directory(tmp_path, monkeypatch):
    """Les chemins par défaut ne doivent jamais viser l'historique de l'utilisateur."""
    monkeypatch.chdir(tmp_path)
