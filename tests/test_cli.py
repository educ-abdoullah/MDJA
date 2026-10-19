import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


def test_cli_downloads_rss_and_writes_json(tmp_path):
    date = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
    (tmp_path / "rss.xml").write_text(
        f'<rss version="2.0"><channel><title>Test</title><item><title>Article</title>'
        f'<link>https://example.org/article</link><pubDate>{date}</pubDate>'
        '</item></channel></rss>', encoding="utf-8",
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path)),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sources = tmp_path / "sources.csv"
    sources.write_text(
        "source_id,name,url,enabled\n"
        f"local,Local,http://127.0.0.1:{server.server_port}/rss.xml,true\n", encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "gazette", "--sources", str(sources),
             "--output", str(tmp_path / "output"), "--run-id", "test-cli"],
            capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        assert result.returncode == 0, result.stderr
        path = json.loads(result.stdout)["output"]
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["run_id"] == "test-cli"
        assert payload["article_count"] == 1
        assert payload["articles"][0]["url"] == "https://example.org/article"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
