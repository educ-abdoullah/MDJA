from pathlib import Path

from gazette.collectors.rss import load_sources


def test_project_catalogue_has_all_eight_sources():
    sources = load_sources(Path("sources.csv"))
    assert len(sources) == 8
    by_id = {source["source_id"]: source for source in sources}
    assert set(by_id) == {"ouest-france", "sud-ouest", "la-provence", "le-telegramme",
                          "franceinfo", "humanite", "liberation", "lemonde"}
    assert by_id["lemonde"]["url"] == "https://www.lemonde.fr/rss/une.xml"
    assert by_id["sud-ouest"]["url"] == "https://www.sudouest.fr/rss.xml"
    assert by_id["le-telegramme"]["url"] == "https://www.letelegramme.fr/arche/rss.xml"
