"""Vrais tests PostgreSQL, actives par TEST_DATABASE_URL ; schema isole par test."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql

from gazette.storage.database import migrate, store_items, sync_sources
from gazette.storage.raw import parse_raw_items


@pytest.fixture
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Lancer docker compose run --rm --build storage-tests pour PostgreSQL")
    connection = psycopg2.connect(url)
    schema = "test_step2_" + uuid4().hex
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    connection.autocommit = False
    migrate(connection)
    sync_sources(connection, Path("sources.csv"))
    try:
        yield connection, schema, url
    finally:
        connection.rollback()
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        connection.close()


def sample_items():
    data = (Path(__file__).parent / "fixtures/sample_rss.xml").read_bytes()
    return parse_raw_items(data, "lemonde", datetime(2026, 10, 21, 9, tzinfo=UTC))


def test_migration_and_sync_can_be_repeated_without_resetting_state(database):
    connection, _, _ = database
    with connection, connection.cursor() as cursor:
        cursor.execute("UPDATE sources SET actif=false,echecs_consecutifs=3 WHERE id='lemonde'")
    assert migrate(connection) == []
    assert sync_sources(connection, Path("sources.csv")) == 8
    with connection.cursor() as cursor:
        cursor.execute("SELECT actif,echecs_consecutifs FROM sources WHERE id='lemonde'")
        assert cursor.fetchone() == (False, 3)


def test_two_passes_zero_duplicates_and_original_file_preserved(database, tmp_path):
    connection, _, _ = database
    items = sample_items()
    first = store_items(connection, items, tmp_path)
    assert first == {"recus": 5, "ecrits": 4, "ignores": 1, "repares": 0}
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    items[0]["titre"] = "Titre change lors du passage suivant"
    second = store_items(connection, items, tmp_path)
    assert second == {"recus": 5, "ecrits": 0, "ignores": 5, "repares": 0}
    assert before == {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM articles_bruts_index")
        assert cursor.fetchone()[0] == 4


def test_file_written_before_rollback_is_reconciled(database, tmp_path):
    connection, _, _ = database
    item = sample_items()[0]
    store_items(connection, [item], tmp_path)
    with connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM articles_bruts_index")
    result = store_items(connection, [item], tmp_path)
    assert result["ignores"] == 1
    assert len(list(tmp_path.rglob("*.json"))) == 1
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM articles_bruts_index")
        assert cursor.fetchone()[0] == 1


def test_missing_file_is_repaired(database, tmp_path):
    connection, _, _ = database
    item = sample_items()[0]
    store_items(connection, [item], tmp_path)
    path = next(tmp_path.rglob("*.json"))
    path.unlink()
    assert store_items(connection, [item], tmp_path)["repares"] == 1
    assert json.loads(path.read_text(encoding="utf-8"))["id"] == item["id"]


def test_concurrent_writers_cannot_duplicate_same_article(database, tmp_path):
    _, schema, url = database
    item = sample_items()[0]

    def write():
        connection = psycopg2.connect(url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            return store_items(connection, [item], tmp_path)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: write(), range(2)))
    assert sum(result["ecrits"] for result in results) == 1
    assert sum(result["ignores"] for result in results) == 1
    assert len(list(tmp_path.rglob("*.json"))) == 1
