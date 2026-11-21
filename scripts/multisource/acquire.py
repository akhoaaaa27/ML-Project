"""Download only explicitly published xGTables CSV links to ignored staging.

Network access is explicit: python -m scripts.multisource.acquire --download
No retries, credentials, API endpoints, per-match scraping or StrikerAPI calls.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "data/external/multisource"
PAGES = {
    "archive": "https://www.xgtables.io/understat-data/",
    "current": "https://www.xgtables.io/data/la-liga/2026/",
    "sources": "https://www.xgtables.io/sources/",
    "directory": "https://www.xgtables.io/data/",
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(v for k, v in attrs if k == "href" and v)


def discover(page_url, html):
    parser = Links()
    parser.feed(html)
    urls = {urljoin(page_url, href) for href in parser.hrefs}
    return sorted(url for url in urls if urlparse(url).hostname == "www.xgtables.io" and (
        re.fullmatch(r"/history/la-liga/20(?:19|2[0-5])/fixtures\.csv", urlparse(url).path)
        or urlparse(url).path == "/history/la-liga/2025/shots.csv"
        or urlparse(url).path == "/data/v1/la-liga/2026/fixtures.csv"))


def acquire(destination=LOCAL):
    destination = Path(destination)
    if (destination / "acquisition_manifest.json").exists():
        raise ValueError("Existing acquisition is immutable; choose a new version directory")
    raw = destination / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    records, downloads = [], {}

    def fetch(url, filename, parent=None):
        response = requests.get(url, timeout=45)
        record = dict(url=url, discovered_on=parent, file=filename,
                      retrieved_at=datetime.now(timezone.utc).isoformat(), status=response.status_code)
        records.append(record)
        # A block/rate limit is recorded, never worked around or retried.
        response.raise_for_status()
        data = response.content
        (raw / filename).write_bytes(data)
        record.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                      content_type=response.headers.get("Content-Type"),
                      etag=response.headers.get("ETag"), last_modified=response.headers.get("Last-Modified"))
        return response.text

    try:
        for name, page in PAGES.items():
            html = fetch(page, name + ".html")
            if name in {"archive", "current"}:
                for url in discover(page, html):
                    downloads[url] = page
        for url, parent in sorted(downloads.items()):
            parts = urlparse(url).path.split("/")
            filename = ("current_" if "/data/v1/" in url else "archive_") + parts[-2] + "_" + parts[-1]
            fetch(url, filename, parent)
    finally:
        (destination / "acquisition_manifest.json").write_text(
            json.dumps(records, indent=2), encoding="utf-8")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--directory", type=Path, default=LOCAL)
    args = parser.parse_args()
    if not args.download:
        parser.error("Use --download for explicit public CSV acquisition")
    result = acquire(args.directory)
    print(json.dumps([dict(file=r["file"], status=r["status"], bytes=r.get("bytes")) for r in result], indent=2))
