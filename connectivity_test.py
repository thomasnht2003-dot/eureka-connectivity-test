#!/usr/bin/env python3
"""Standalone connectivity test of the data sources from a (throw-away) cloud server. Phase 8.2.

    python3 connectivity_test.py targets.json --rounds 4 --interval 21600 --out results.json

Needs ONLY Python 3.8+ and the standard library. It holds no project code, no project data and no API key: only the public URLs of
targets.json. It identifies itself honestly, respects robots.txt (a 403 on robots.txt means "do not crawl", as in the project), uses at most one
request every 2 seconds, fetches only listing pages and the first 2 KB of two files, and never retries a refusal or tries to get past a block.

Exit code: 0 = every target reachable in every round; 1 = at least one failure (see the summary); 2 = bad input.
"""
from __future__ import annotations

import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit

UA = "EurekaBlueSky/0.5 (+research; connectivity test of public official statistics; contact: owner)"
DELAY_S = 2.0
CHALLENGE_MARKERS = ("just a moment", "request blocked", "cf-chl", "access denied", "attention required", "captcha")
MAGIC = {"pdf": b"%PDF", "xlsx": b"PK\x03\x04", "html": b"<", "json": b"{"}
_last = [0.0]
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def encode(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%:@!$&'()*+,;=-._~"), quote(p.query, safe="=&%:/?+,-._~"), ""))


def _get(url: str, headers: dict, timeout: int = 45) -> tuple[int | None, bytes, dict, str]:
    wait = DELAY_S - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(encode(url), headers=dict({"User-Agent": UA, "Accept": "*/*"}, **headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(400_000), dict(r.headers), ""
    except urllib.error.HTTPError as e:
        return e.code, e.read(4000), dict(e.headers), ""
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as e:
        return None, b"", {}, f"{type(e).__name__}: {e}"[:160]
    finally:
        _last[0] = time.time()


def robots_allows(url: str) -> tuple[bool, str]:
    host = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    if host not in _robots:
        status, body, _, err = _get(host + "/robots.txt", {})
        rp = urllib.robotparser.RobotFileParser()
        if status in (401, 403):
            rp.disallow_all = True
            _robots[host] = rp
            return False, f"robots.txt answered HTTP {status}: by the standard this means do not crawl"
        if status == 200:
            rp.parse(body.decode("utf-8", "ignore").splitlines())
        else:
            rp.allow_all = True
        _robots[host] = rp
    return _robots[host].can_fetch(UA, url), ""


def probe(t: dict) -> dict:
    name, url, kind = t["name"], t["url"], t.get("kind", "html")
    out = {"name": name, "url": url, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    ok, why = robots_allows(url) if t.get("robots", True) else (True, "")
    if not ok:
        return dict(out, status=None, ok=False, verdict="robots_disallow", detail=why or "disallowed by robots.txt")
    headers = {"Range": "bytes=0-2047"} if t.get("range") else {}
    if kind == "json":
        headers["Accept"] = "application/json"
    t0 = time.time()
    status, body, hdrs, err = _get(url, headers)
    out["latency_s"] = round(time.time() - t0, 2)
    out["status"] = status
    text = body[:3000].decode("utf-8", "ignore").lower()
    if err:
        return dict(out, ok=False, verdict="network_error", detail=err)
    if status in (403, 429, 503) and any(m in text for m in CHALLENGE_MARKERS):
        return dict(out, ok=False, verdict="bot_challenge_or_block", detail=f"HTTP {status} with a block/challenge page (not bypassed)", bytes=len(body))
    if status == 403:
        return dict(out, ok=False, verdict="forbidden", detail="HTTP 403", bytes=len(body))
    if status == 429:
        return dict(out, ok=False, verdict="rate_limited", detail="HTTP 429", bytes=len(body))
    if status not in (200, 206):
        return dict(out, ok=False, verdict="unexpected_status", detail=f"HTTP {status}", bytes=len(body))
    magic = MAGIC.get(kind)
    if magic and not body.lstrip()[: len(magic)].startswith(magic) and not body.startswith(magic):
        return dict(out, ok=False, verdict="wrong_content", detail=f"content does not look like {kind}: starts with {body[:8]!r}", bytes=len(body))
    if len(body) < t.get("min_bytes", 1):
        return dict(out, ok=False, verdict="too_small", detail=f"{len(body)} bytes", bytes=len(body))
    if t.get("must_contain") and t["must_contain"].lower() not in body.decode("utf-8", "ignore").lower():
        return dict(out, ok=False, verdict="wrong_content", detail=f"missing expected text {t['must_contain']!r}", bytes=len(body))
    return dict(out, ok=True, verdict="ok", bytes=len(body))


def environment() -> dict:
    env = {"hostname": socket.gethostname(), "python": sys.version.split()[0], "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    status, body, _, err = _get("https://api.ipify.org", {}, 20)
    env["public_ip"] = body.decode().strip() if status == 200 else None
    return env


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    args = {"rounds": 1, "interval": 0, "out": "results.json"}
    i = 2
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k in args and i + 1 < len(argv):
            args[k] = type(args[k])(argv[i + 1])
            i += 2
        else:
            print("unknown option", argv[i])
            return 2
    targets = json.load(open(argv[1], encoding="utf-8"))["targets"]
    report = {"environment": environment(), "rounds": []}
    for r in range(args["rounds"]):
        res = [probe(t) for t in targets]
        report["rounds"].append({"round": r + 1, "results": res})
        print(f"round {r + 1}/{args['rounds']}: " + ", ".join(f"{x['name']}={'ok' if x['ok'] else x['verdict']}" for x in res), flush=True)
        json.dump(report, open(args["out"], "w", encoding="utf-8"), indent=1)
        if r + 1 < args["rounds"]:
            time.sleep(args["interval"])
    allr = [x for rd in report["rounds"] for x in rd["results"]]
    summary = {n: {"ok": sum(1 for x in allr if x["name"] == n and x["ok"]), "of": sum(1 for x in allr if x["name"] == n),
                   "median_latency_s": sorted(x.get("latency_s", 0) for x in allr if x["name"] == n)[len([1 for x in allr if x["name"] == n]) // 2],
                   "verdicts": sorted({x["verdict"] for x in allr if x["name"] == n})} for n in {x["name"] for x in allr}}
    report["summary"] = summary
    report["all_ok"] = all(x["ok"] for x in allr)
    json.dump(report, open(args["out"], "w", encoding="utf-8"), indent=1)
    print(json.dumps(summary, indent=1))
    print("RESULT:", "ALL REACHABLE" if report["all_ok"] else "PROBLEMS FOUND (see the verdicts)")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
