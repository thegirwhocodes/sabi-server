#!/usr/bin/env python3
"""Serve local test artifacts with HTTP byte-range support for media players."""

from __future__ import annotations

import argparse
from email.utils import formatdate
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
from typing import BinaryIO


class RangeRequestHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, directory: str | None = None, **kwargs) -> None:
        self._byte_range: tuple[int, int] | None = None
        super().__init__(*args, directory=directory, **kwargs)

    def send_head(self) -> BinaryIO | None:
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            source = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        stat = os.fstat(source.fileno())
        size = stat.st_size
        content_type = self.guess_type(path)
        range_header = self.headers.get("Range", "")
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if match and size:
            raw_start, raw_end = match.groups()
            if not raw_start and not raw_end:
                match = None
            elif not raw_start:
                suffix = min(size, int(raw_end))
                start, end = size - suffix, size - 1
            else:
                start = int(raw_start)
                end = min(size - 1, int(raw_end)) if raw_end else size - 1
                if start >= size or end < start:
                    source.close()
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return None
            if match:
                self._byte_range = (start, end)
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
                self.end_headers()
                return source

        self._byte_range = None
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
        self.end_headers()
        return source

    def copyfile(self, source: BinaryIO, outputfile: BinaryIO) -> None:
        if self._byte_range is None:
            return super().copyfile(source, outputfile)
        start, end = self._byte_range
        source.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            block = source.read(min(64 * 1024, remaining))
            if not block:
                break
            outputfile.write(block)
            remaining -= len(block)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    handler = lambda *handler_args, **handler_kwargs: RangeRequestHandler(  # noqa: E731
        *handler_args,
        directory=str(args.directory),
        **handler_kwargs,
    )
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
