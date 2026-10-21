from datetime import UTC, datetime
from pathlib import Path

import pytest

from gazette.catalogue import read_catalogue
from gazette.storage.raw import article_id, parse_raw_items

NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)


def test_raw_items_keep_old_future_and_undated_items():
    data = (Path(__file__).parent / "fixtures/sample_rss.xml").read_bytes()
    items = parse_raw_items(data, "lemonde", NOW)
    assert len(items) == 5  # Seul le lien javascript est hors contrat.
    assert any(item["titre"] == "Ancien" for item in items)
    assert any(item["titre"] == "Futur" for item in items)
    assert next(item for item in items if item["titre"] == "Sans date")["publie_le"] is None
    assert items[0]["id"] == items[1]["id"]  # Le stockage deduplique, pas le parseur brut.


def test_raw_empty_title_and_bounded_metadata_without_media_content():
    xml = f'''<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
    <channel><item><link>https://example.org/test</link><description>{'a' * 2100}</description>
    <content:encoded>ARTICLE INTEGRAL INTERDIT</content:encoded>
    <enclosure url="https://example.org/image.jpg"/></item></channel></rss>'''.encode()
    item = parse_raw_items(xml, "lemonde", NOW)[0]
    assert item["titre"] == ""
    assert len(item["resume"]) == 2000
    assert item["payload"]["resume_tronque"] is True
    assert "ARTICLE INTEGRAL" not in str(item)
    assert "image.jpg" not in str(item)
    assert set(item) == {"id", "source", "lien", "titre", "resume", "publie_le",
                         "recupere_le", "rubrique", "payload"}


def test_raw_atom_and_timezone():
    xml = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>id-1</id>
    <link href="https://example.org/atom"/><title>Test</title>
    <updated>2026-10-21T10:00:00+02:00</updated><summary>Extrait</summary>
    <category term="Societe"/></entry></feed>'''
    item = parse_raw_items(xml, "franceinfo", NOW)[0]
    assert item["publie_le"] == "2026-10-21T08:00:00+00:00"
    assert item["rubrique"] == ["Societe"]
    assert item["payload"]["guid_ou_id"] == "id-1"


def test_source_is_part_of_identity():
    assert article_id("lemonde", "https://example.org/a") != article_id(
        "franceinfo", "https://example.org/a",
    )


def test_full_content_is_never_used_as_summary_fallback():
    xml = b'''<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
    <channel><item><link>https://example.org/a</link>
    <content:encoded>ARTICLE INTEGRAL</content:encoded></item></channel></rss>'''
    item = parse_raw_items(xml, "lemonde", NOW)[0]
    assert item["resume"] == ""
    assert "ARTICLE INTEGRAL" not in str(item)


def test_french_catalogue_preserves_notes_and_all_sources():
    sources = read_catalogue(Path("sources.csv"))
    assert len(sources) == 8
    assert all(source["active"] for source in sources)
    assert sources[0]["conditions"].startswith("Réservé")
    assert next(s for s in sources if s["source_id"] == "humanite")["name"] == "L'Humanité"


@pytest.mark.parametrize("source", ["../bad", ""])
def test_raw_rejects_invalid_source_ids(source):
    with pytest.raises(ValueError):
        parse_raw_items(b"<rss/>", source, NOW)
