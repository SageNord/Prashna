"""One-off, body-safe PIB feed diagnostic. Run from the backend directory."""
from __future__ import annotations

import json
import socket
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.sources import configured_sources

MAX_DIAGNOSTIC_BYTES = 10_000_000
CHUNK_SIZE = 64 * 1024


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def safe_reason(error: BaseException) -> str:
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "request timed out"
    if isinstance(reason, ssl.SSLError):
        return "TLS connection failed"
    if isinstance(reason, socket.gaierror):
        return "DNS lookup failed"
    if isinstance(reason, OSError):
        return f"network OS error ({reason.errno})" if reason.errno is not None else "network OS error"
    return type(reason).__name__


def main() -> None:
    source = next(s for s in configured_sources() if s.name == "Press Information Bureau")
    request = Request(source.url, headers={
        # Match the production fetcher's public request headers. No secrets are used.
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    response = None
    http_error = None
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as exc:
        # HTTPError is also a response; collect only metadata and bounded bytes.
        response = exc
        http_error = exc
    except (URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError) as exc:
        print(json.dumps({"https_connected": False, "error": safe_reason(exc)}, sort_keys=True))
        return

    body = bytearray()
    byte_count = 0
    complete = True
    try:
        while True:
            chunk = response.read(min(CHUNK_SIZE, MAX_DIAGNOSTIC_BYTES + 1 - byte_count))
            if not chunk:
                break
            byte_count += len(chunk)
            body.extend(chunk)
            if byte_count > MAX_DIAGNOSTIC_BYTES:
                complete = False
                break
    finally:
        response.close()

    root_tag = None
    item_count = 0
    xml_parsed = False
    parse_error = None
    if complete:
        try:
            root = ET.fromstring(body)
            root_tag = root.tag
            item_count = sum(1 for node in root.iter() if local_name(node.tag) in {"item", "entry"})
            xml_parsed = True
        except ET.ParseError:
            parse_error = "response is not well-formed XML"
    else:
        parse_error = "response exceeded diagnostic byte limit; XML parsing skipped"

    root_local = local_name(root_tag) if root_tag else None
    print(json.dumps({
        "https_connected": True,
        "http_status": response.status,
        "content_type": response.headers.get("Content-Type"),
        "response_bytes": byte_count,
        "response_complete": complete,
        "xml_parsed": xml_parsed,
        "appears_rss_or_atom": bool(xml_parsed and (root_local in {"rss", "rdf", "feed"} or item_count > 0)),
        "xml_root_tag": root_tag,
        "item_entry_count": item_count if xml_parsed else None,
        "parse_note": parse_error,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
