#!/usr/bin/env python3
"""Serve the static PD Insighter demo with byte-range video support."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


class RangeRequestHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        self._byte_range: tuple[int, int] | None = None
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Accept-Ranges", "bytes")
        if self.path.endswith(".html"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            return super().send_head()
        try:
            source = path.open("rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        size = path.stat().st_size
        content_type = self.guess_type(str(path))
        range_header = self.headers.get("Range", "")
        match = RANGE_RE.fullmatch(range_header.strip()) if range_header else None
        if match:
            first, last = match.groups()
            if first:
                start = int(first)
                end = int(last) if last else size - 1
            elif last:
                length = min(int(last), size)
                start = size - length
                end = size - 1
            else:
                source.close()
                self.send_error(416, "Invalid byte range")
                return None
            if start >= size or start > end:
                source.close()
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return None
            end = min(end, size - 1)
            self._byte_range = (start, end)
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
            self.end_headers()
            source.seek(start)
            return source

        self._byte_range = None
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
        self.end_headers()
        return source

    def copyfile(self, source, outputfile) -> None:
        if self._byte_range is None:
            shutil.copyfileobj(source, outputfile)
            return
        start, end = self._byte_range
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.bind, args.port), RangeRequestHandler)
    url = f"http://{args.bind}:{args.port}/"
    print(f"PD Insighter demo: {url}")
    print("Press Control+C to stop.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
