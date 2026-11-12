"""Régressions TD4 et validation du traitement réel en PostgreSQL."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from gazette.processing.normalize import normalize_article
from gazette.processing.quality_checks import read_integrity_counts
from gazette.processing.rules import FUTURE_TOLERANCE, evaluate_article, filter_articles


def article(
    title, summary="Un résumé commun détaillé de cette actualité importante", source="lemonde"
):
    return {"source": source, "titre": title, "resume": summary}


def test_near_duplicates_and_distinct_sources():
    title = "Le gouvernement annonce une nouvelle réforme nationale du système de santé"
    changed = title + " publique"
    kept, rejected = filter_articles([article(title), article(changed)])
    assert len(kept) == 1
    assert rejected[0].rule_id == "R10_doublon_approximatif"
    kept, rejected = filter_articles([article(title), article(changed, source="liberation")])
    assert len(kept) == 2 and not rejected
    kept, rejected = filter_articles([article(title), article(changed, summary="Un autre angle")])
    assert len(kept) == 2 and not rejected


def test_future_tolerance_matches_sql():
    now = datetime.now(UTC)
    item = normalize_article({**article("Actualité"), "publie_le": now + FUTURE_TOLERANCE})
    assert evaluate_article(item, now=now).accepted
    item["publie_le"] = (now + FUTURE_TOLERANCE + timedelta(seconds=1)).isoformat()
    assert evaluate_article(item, now=now).rule_id == "R06_date_future"
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (0,)
    read_integrity_counts(connection)
    calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    assert any("INTERVAL '1 second'" in c.args[0] and c.args[1] == (300.0,) for c in calls)


def test_quality_rebuild_on_postgres(database, tmp_path, monkeypatch):
    """Exécuter le vrai SQL dans le schéma isolé fourni par les tests de stockage."""
    import psycopg2

    from gazette.processing.persist import rebuild_quality
    from gazette.processing.quality_checks import run_checks
    from gazette.storage.database import store_items

    connection, schema, url = database
    now = datetime.now(UTC)
    from gazette.storage.raw import parse_raw_items

    xml = b"""<rss version="2.0"><channel><title>Test</title>
    <item><title>Actualite nationale</title><link>https://example.org/a</link></item>
    <item><title>QUIZ. Test</title><link>https://example.org/b</link></item>
    </channel></rss>"""
    store_items(connection, parse_raw_items(xml, "lemonde", now), tmp_path)
    real_connect = psycopg2.connect

    def connect(*args, **kwargs):
        return real_connect(*args, **kwargs, options=f"-c search_path={schema}")

    monkeypatch.setattr(psycopg2, "connect", connect)
    assert rebuild_quality(url, tmp_path)["rejetes"] == 1
    assert rebuild_quality(url, tmp_path)["conserves"] == 1
    assert run_checks(url)["statut"] == "OK"


@pytest.fixture
def database(request):
    # Réutiliser la fixture qui gère création et nettoyage du schéma PostgreSQL.
    from test_postgres_storage import database as storage_database

    yield from storage_database.__wrapped__()
