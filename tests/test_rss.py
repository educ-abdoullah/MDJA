import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gazette.collectors import rss

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rss.xml"
SOURCE = {"source_id": "test", "name": "Test", "url": "https://example.org/rss"}
NOW = datetime(2026, 10, 19, 5, tzinfo=UTC)


def test_filters_duplicates_old_future_undated_and_invalid_links():
    articles = rss.parse_articles(FIXTURE.read_bytes(), SOURCE, NOW)
    assert len(articles) == 1
    assert articles[0]["title"] == "Article récent"
    assert articles[0]["published_at"] == "2026-10-19T04:30:00+00:00"


@pytest.mark.parametrize("content", [b"broken", b"<html>Not RSS</html>", b"<rss>"])
def test_rejects_invalid_feeds(content):
    with pytest.raises(ValueError, match="invalide"):
        rss.parse_articles(content, SOURCE, NOW)


def test_atom_and_timezone_conversion():
    content = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Test</title>
    <entry><title>Atom</title><link href="https://example.org/atom"/>
    <updated>2026-10-19T06:30:00+02:00</updated></entry></feed>'''
    assert rss.parse_articles(content, SOURCE, NOW)[0]["published_at"] == NOW.replace(
        hour=4, minute=30,
    ).isoformat()


def test_retry_replaces_same_archive_without_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(rss, "fetch_feed", lambda url: FIXTURE.read_bytes())
    monkeypatch.setattr(rss, "parse_articles", lambda *args: [{"title": "Test"}])
    first = rss.collect_source(SOURCE, tmp_path, "manual/run:1")
    second = rss.collect_source(SOURCE, tmp_path, "manual/run:1")
    assert first == second
    assert len(list(tmp_path.rglob("*.json"))) == 1
    assert not list(tmp_path.rglob("*.tmp"))
    assert json.loads(Path(first).read_text(encoding="utf-8"))["article_count"] == 1
    assert rss.collect_source(SOURCE, tmp_path, "manual/run:2") != first


def test_network_failure_propagates_for_airflow_retry(tmp_path, monkeypatch):
    def unavailable(url):
        raise TimeoutError("Source indisponible")

    monkeypatch.setattr(rss, "fetch_feed", unavailable)
    with pytest.raises(TimeoutError):
        rss.collect_source(SOURCE, tmp_path, "run")
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("rows", [
    "test,Test,https://example.org/rss,false",
    "../bad,Test,https://example.org/rss,true",
    "test,Test,file:///etc/passwd,true",
    "test,Test,https://example.org/rss,yes",
    "test,Test,https://example.org/rss,true\ntest,Test,https://example.org/rss,true",
])
def test_rejects_invalid_source_configuration(tmp_path, rows):
    path = tmp_path / "sources.csv"
    path.write_text("source_id,name,url,enabled\n" + rows, encoding="utf-8")
    with pytest.raises(ValueError):
        rss.load_sources(path)


def test_loads_enabled_sources(tmp_path):
    path = tmp_path / "sources.csv"
    path.write_text(
        "source_id,name,url,enabled\ntest,Test,https://example.org/rss,true\n"
        "off,Off,https://example.org/off,false\n", encoding="utf-8",
    )
    assert rss.load_sources(path) == [SOURCE]
