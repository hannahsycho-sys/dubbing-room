#!/usr/bin/env python3
"""
serve.py — 영상 탐색(seek)이 되는 간단한 로컬 서버.

파이썬 기본 http.server 는 Range 요청을 무시해서, 브라우저가 영상 중간으로
건너뛸 수 없습니다(더빙은 구간 이동이 생명이라 치명적입니다).
이 서버는 Range 를 제대로 처리합니다.

    python3 ~/더빙/serve.py          # 4321 포트
    python3 ~/더빙/serve.py 5000     # 포트 지정
"""
import os, re, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))


class RangeHandler(SimpleHTTPRequestHandler):
    # HTTP/1.0 은 요청마다 연결을 끊어서, 영상처럼 조각을 계속 받아오는 경우
    # 버퍼 경계에서 재생이 멈출 수 있다. 1.1 로 올려 연결을 유지한다.
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path) or not os.path.exists(path):
            return super().send_head()

        m = re.match(r"bytes=(\d*)-(\d*)\s*$", rng)
        if not m:
            return super().send_head()

        size = os.path.getsize(path)
        first, last = m.group(1), m.group(2)
        if first == "":                       # bytes=-N  (끝에서 N바이트)
            length = min(int(last or 0), size)
            start, end = size - length, size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1
        end = min(end, size - 1)

        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._remain = end - start + 1
        return f

    def copyfile(self, src, dst):
        remain = getattr(self, "_remain", None)
        if remain is None:
            return super().copyfile(src, dst)
        self._remain = None
        while remain > 0:
            chunk = src.read(min(64 * 1024, remain))
            if not chunk:
                break
            dst.write(chunk)
            remain -= len(chunk)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4321
    print(f"  {ROOT} 를 http://localhost:{port}/ 로 서비스합니다")
    print(f"  더빙룸  →  http://localhost:{port}/collab/")
    print("  멈추려면 Ctrl+C")
    ThreadingHTTPServer(("", port), RangeHandler).serve_forever()
