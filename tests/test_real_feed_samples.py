from datetime import UTC, datetime
from pathlib import Path

import pytest

from gazette.collectors.rss import parse_articles


@pytest.mark.parametrize(("source_id", "expected_utc"), [
    ("lemonde", "2026-10-21T04:51:13+00:00"),
    ("franceinfo", "2026-10-21T06:50:12+00:00"),
])
def test_saved_real_rss_samples_are_understood(source_id, expected_utc):
    sample = Path(__file__).parent / "fixtures" / f"{source_id}_sample_rss.xml"
    source = {"source_id": source_id, "name": source_id}
    articles = parse_articles(sample.read_bytes(), source, datetime(2026, 10, 21, 9, tzinfo=UTC))
    assert len(articles) == 1
    assert articles[0]["source_id"] == source_id
    assert articles[0]["title"]
    assert articles[0]["url"].startswith("https://www.")
    assert articles[0]["published_at"] == expected_utc
