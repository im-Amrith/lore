from pathlib import Path

import pytest

from lore.config import graph_name
from lore.graph.queries import load_query


def test_load_query_by_short_and_full_name():
    assert "Healthcheck" in load_query("healthcheck")
    assert load_query("healthcheck") == load_query("00_healthcheck")


def test_load_query_unknown_name():
    with pytest.raises(KeyError):
        load_query("does_not_exist")


def test_duplicate_names_rejected(tmp_path: Path):
    (tmp_path / "01_same.cypher").write_text("RETURN 1", encoding="utf-8")
    (tmp_path / "02_same.cypher").write_text("RETURN 2", encoding="utf-8")
    with pytest.raises(ValueError):
        load_query("same", tmp_path)


def test_graph_name_is_lowercase():
    assert graph_name("FalkorDB") == "lore_falkordb"
