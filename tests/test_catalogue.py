from pathlib import Path

from gazette.collectors.rss import load_sources


def test_project_catalogue_has_one_usable_source():
    sources = load_sources(Path("sources.csv"))
    assert len(sources) == 1
    assert sources[0]["source_id"] == "lemonde"
    assert sources[0]["url"] == "https://www.lemonde.fr/rss/une.xml"
