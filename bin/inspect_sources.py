"""Observer deux flux reels sans activer de source ni modifier le collecteur."""

import argparse
import calendar
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import feedparser

MAX_BYTES = 5 * 1024 * 1024


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def inspect_source(source_id, url, fixtures_dir=None, refresh_fixtures=False):
    result = {"source_id": source_id, "requested_url": url}
    request = Request(url, headers={"User-Agent": "GazetteMDJA/0.1 (RSS educational project)"})
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read(MAX_BYTES + 1)
            result.update({
                "http_status": response.status,
                "final_url": response.url,
                "content_type": response.headers.get("Content-Type"),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "bytes_received": len(content),
            })
        if len(content) > MAX_BYTES:
            raise ValueError("Flux superieur a 5 Mio")
        feed = feedparser.parse(content)
        root = ElementTree.fromstring(content)
        raw_items = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
        raw_fields = Counter(local_name(child.tag) for item in raw_items for child in item)
        qualified_fields = Counter(child.tag for item in raw_items for child in item)
        normalized_fields = (
            "id", "title", "link", "published", "published_parsed", "updated",
            "updated_parsed", "summary", "content", "tags",
        )
        first = feed.entries[0] if feed.entries else {}
        first_raw = raw_items[0] if raw_items else []
        date_fields = {local_name(child.tag): child.text for child in first_raw
                       if local_name(child.tag) in {"pubDate", "published", "updated", "date"}}
        parsed_date = first.get("published_parsed") or first.get("updated_parsed")
        published_utc = (
            datetime.fromtimestamp(calendar.timegm(parsed_date), UTC).isoformat()
            if parsed_date else None
        )
        result.update({
            "feed_format": feed.version,
            "encoding_detected": feed.get("encoding"),
            "parser_reports_issue": bool(feed.bozo),
            "parser_issue": str(feed.get("bozo_exception", "")),
            "items_received": len(feed.entries),
            "raw_item_fields_occurrences": dict(sorted(raw_fields.items())),
            "qualified_item_fields_occurrences": dict(sorted(qualified_fields.items())),
            "normalized_fields_present": {
                field: sum(field in item for item in feed.entries) for field in normalized_fields
            },
            "first_item": {
                "id": first.get("id"),
                "link": first.get("link"),
                "raw_dates": date_fields,
                "published_utc": published_utc,
                "title_characters": len(first.get("title", "")),
                "summary_characters": len(first.get("summary", "")),
                "summary_format": first.get("summary_detail", {}).get("type"),
                "rubriques": [tag.get("term") for tag in first.get("tags", [])],
            },
            "usable_feed": bool(feed.version and feed.entries and not feed.bozo),
        })
        if fixtures_dir is not None and raw_items and feed.version == "rss20" and not feed.bozo:
            # Echantillon reduit : aucun media:content, enclosure, image ou texte integral.
            sample = ElementTree.Element("rss", version="2.0")
            channel = ElementTree.SubElement(sample, "channel")
            ElementTree.SubElement(channel, "title").text = source_id
            ElementTree.SubElement(channel, "link").text = response.url
            ElementTree.SubElement(channel, "description").text = "Exemple reel reduit, etape 1"
            item = ElementTree.SubElement(channel, "item")
            for child in raw_items[0]:
                if child.tag in {"guid", "link", "title", "description", "pubDate", "category"}:
                    selected = ElementTree.SubElement(item, child.tag, child.attrib)
                    selected.text = child.text
            fixtures_dir.mkdir(parents=True, exist_ok=True)
            path = fixtures_dir / f"{source_id}_sample_rss.xml"
            ElementTree.indent(sample)
            if refresh_fixtures or not path.exists():
                ElementTree.ElementTree(sample).write(path, encoding="utf-8", xml_declaration=True)
            result["reduced_fixture"] = str(path)
    except HTTPError as error:
        result.update({"http_status": error.code, "error": str(error), "usable_feed": False})
    except (URLError, TimeoutError, ValueError, ElementTree.ParseError) as error:
        result.update({"error": str(error), "usable_feed": False})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/diagnostics/etape1-flux.json"))
    parser.add_argument("--fixtures-dir", type=Path, default=None)
    parser.add_argument("--refresh-fixtures", action="store_true")
    parser.add_argument("--catalogue", type=Path, default=Path("sources.csv"))
    parser.add_argument("--all-sources", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from gazette.catalogue import read_catalogue

    sources = read_catalogue(args.catalogue)
    if not args.all_sources:
        sources = [row for row in sources if row["source_id"] in {"lemonde", "franceinfo"}]
    report = {
        "observed_at": datetime.now(UTC).isoformat(),
        "sources": [inspect_source(row["source_id"], row["url"], args.fixtures_dir,
                                   args.refresh_fixtures) for row in sources],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Rapport local : {args.output}")
    return 0 if all(source["usable_feed"] for source in report["sources"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
