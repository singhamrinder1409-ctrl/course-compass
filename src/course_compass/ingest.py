"""Import a pinned UVic calendar sample; Python standard library only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

CATALOG_ID = "69bd9d92e76504efd3e57c74"
EDITION = "September 2026"
BASE = "https://uvic.kuali.co/api/v1/catalog"
LANDING = "https://www.uvic.ca/calendar/undergrad/index.php"
SAMPLE = ("CSC110", "CSC115", "CSC225", "CSC226", "CSC320", "CSC360")
ROOT = Path(__file__).resolve().parents[2]


class TextExtractor(HTMLParser):
    """Retain list boundaries and inline spacing without executing HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
        self.list_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"ul", "ol"}:
            self.list_depth += 1
        if tag in {"p", "div", "ul", "ol", "li", "br"}:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("  " * max(0, self.list_depth - 1) + "• ")

    def handle_endtag(self, tag):
        if tag in {"ul", "ol"}:
            self.list_depth = max(0, self.list_depth - 1)
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "ul", "ol", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(html):
    if not isinstance(html, str):
        raise ValueError("Expected an HTML string")
    parser = TextExtractor()
    parser.feed(html)
    lines = []
    for raw in "".join(parser.parts).splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        line = re.sub(r"\s+", " ", raw).strip()
        if lines and lines[-1].strip() == "•" and not line.startswith("•"):
            lines[-1] += " " + line
        else:
            lines.append(" " * indent + line)
    return "\n".join(lines)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url):
    request = Request(url, headers={"User-Agent": "CourseCompass/0.1 (local educational prototype)"})
    with urlopen(request, timeout=30) as response:
        data = response.read()
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        return data


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def normalize(course, expected_code, schema, raw_bytes, retrieved_at, api_url):
    if course.get("__catalogCourseId") != expected_code:
        raise ValueError(f"Course identity mismatch for {expected_code}")
    if course.get("__passedCatalogQuery") is not True:
        raise ValueError(f"Course is outside the pinned catalog: {expected_code}")
    if course.get("subjectCode", {}).get("name") != "CSC":
        raise ValueError("Unexpected subject")
    if not course.get("pid") or not course.get("title"):
        raise ValueError("Missing course identity or title")
    description = plain_text(course.get("description", ""))
    if not description:
        raise ValueError(f"Empty description for {expected_code}")
    # Use the catalog's field labels; keep every nonempty textual field.
    # This includes notes and requirements that would be lost by selecting
    # only description and prerequisites.
    sections = []
    for key, value in course.items():
        if key.startswith("_") or key in {"pid", "id", "title", "proForma", "dateStart", "catalogActivationDate"}:
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        text = plain_text(value)
        if not text:
            continue
        label = schema.get(key, {}).get("label", key)
        section_id = f"{CATALOG_ID}:{course['pid']}:{key}"
        sections.append({"id": section_id, "field": key, "label": label, "text": text,
                         "source_html": value, "text_sha256": digest(text.encode())})
    return {
        "course_code": expected_code, "title": course["title"],
        "catalog_id": CATALOG_ID, "calendar_edition": EDITION,
        "pid": course["pid"], "record_id": course["id"],
        "source_url": f"{LANDING}#/courses/{course['pid']}",
        "api_url": api_url, "retrieved_at": retrieved_at,
        "raw_sha256": digest(raw_bytes),
        "credits": course.get("credits"), "sections": sections,
        "quality_flags": (["Editorial instruction appears in source description"]
                          if "change the description to" in description.lower() else []),
    }


def run(output, offline=False):
    raw = output / "raw" / CATALOG_ID
    processed = output / "processed" / CATALOG_ID
    raw.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = {"catalog_id": CATALOG_ID, "calendar_edition": EDITION,
                "run_at": timestamp, "offline": offline, "courses": [], "failures": []}

    def obtain(name, url):
        path = raw / name
        if offline:
            data = path.read_bytes()
        else:
            time.sleep(0.3)
            data = fetch(url)
            # Check JSON before replacing a useful local snapshot.
            json.loads(data)
            path.write_bytes(data)
            save_json(raw / (name + ".provenance.json"),
                      {"url": url, "retrieved_at": timestamp, "sha256": digest(data)})
        provenance = json.loads((raw / (name + ".provenance.json")).read_text())
        if provenance["sha256"] != digest(data) or provenance["url"] != url:
            raise ValueError(f"Snapshot provenance mismatch: {name}")
        return json.loads(data), data, provenance["retrieved_at"]

    try:
        catalog, _, _ = obtain("catalog.json", f"{BASE}/public/catalogs/{CATALOG_ID}")
        if catalog.get("_id") != CATALOG_ID or catalog.get("title") != f"Undergraduate Calendar - {EDITION}":
            raise ValueError("Calendar identity mismatch")
        schema, _, _ = obtain("schema.json", f"{BASE}/schema/{CATALOG_ID}/courses")
        listing, _, _ = obtain("listing.json", f"{BASE}/courses/{CATALOG_ID}?q=CSC")
        if not isinstance(listing, list):
            raise ValueError("Course listing is not a list")
        for code in SAMPLE:
            try:
                matches = [row for row in listing if row.get("__catalogCourseId") == code]
                if len(matches) != 1:
                    raise ValueError(f"Expected one listing for {code}, found {len(matches)}")
                url = f"{BASE}/course/{CATALOG_ID}/{matches[0]['pid']}"
                course, data, retrieved_at = obtain(f"{code}.json", url)
                record = normalize(course, code, schema, data, retrieved_at, url)
                manifest["courses"].append(record)
            except (OSError, ValueError, KeyError, TypeError) as error:
                manifest["failures"].append({"course_code": code, "error": str(error)})
    except (OSError, ValueError, KeyError, TypeError) as error:
        manifest["failures"].append({"stage": "catalog", "error": str(error)})
    save_json(processed / "manifest.json", manifest)
    # Publish a corpus only when the whole sample passes validation.
    if manifest["failures"]:
        print(json.dumps(manifest["failures"], indent=2), file=sys.stderr)
        return 1
    save_json(processed / "courses.json", manifest["courses"])
    print(f"Imported {len(manifest['courses'])} courses into {processed}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Rebuild from verified local snapshots")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    return run(args.data_dir, args.offline)


if __name__ == "__main__":
    raise SystemExit(main())
