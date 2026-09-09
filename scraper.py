"""Daily official-source fetcher. Python 3.11+, standard library only."""
from __future__ import annotations
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parent
UA = "VPSDealsBot/1.0 (+https://github.com/holaclea/vps-deals-promo-radar)"
MAX_BYTES = 3_000_000

class Node:
    def __init__(self, tag="root", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
    def text(self):
        return re.sub(r"\s+", " ", " ".join(c.text() if isinstance(c, Node) else c for c in self.children)).strip()
    def find(self, tag=None):
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.find(tag)

class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        if not any(n.tag in {"script", "style", "noscript"} for n in self.stack):
            self.stack[-1].children.append(data)

def price(text):
    match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)\s*(?:/|per\s+)\s*(year|month|yr|mo)\b", text, re.I)
    if not match:
        raise ValueError("unambiguous USD billing price missing")
    amount = Decimal(match[1])
    if amount <= 0:
        raise ValueError("nonpositive price")
    return str(amount), "year" if match[2].lower() in {"year", "yr"} else "month"

def record(provider, title, text, specs, now, digest):
    amount, period = price(text)
    key = hashlib.sha256((provider["id"] + ":" + title).encode()).hexdigest()[:12]
    return {"id": provider["id"] + "-" + key, "provider_id": provider["id"], "title": title,
            "price": amount, "currency": "USD", "billing_period": period,
            "kind": provider["kind"], "specs": specs, "offer_url": provider["source_url"],
            "source_url": provider["source_url"], "source_sha256": digest,
            "evidence": text, "valid_from": None, "valid_until": None,
            "renewal_price": None, "tax_included": None, "availability": "not_checked",
            "checked_at": now, "first_seen_at": now, "last_seen_at": now, "status": "observed"}

def parse(provider, html, now, digest):
    root = Document(html).root
    offers = []
    if provider["adapter"] == "buyvm":
        for node in root.find("div"):
            if "plan" not in node.attrs.get("class", "").split():
                continue
            headings = list(node.find("h2"))
            if not headings or not re.fullmatch(r"SLICE \d+", headings[0].text()):
                continue
            specs = [li.text() for li in node.find("li") if li.text() and "$" not in li.text()]
            text = " ".join(li.text() for li in node.find("li") if "$" in li.text())
            offers.append(record(provider, headings[0].text(), text, specs, now, digest))
    elif provider["adapter"] == "ramnode":
        for section in root.find("section"):
            headings = list(section.find("h2"))
            if not headings or not headings[0].text().startswith("Standard VPS"):
                continue
            for row in section.find("tr"):
                cells = [c.text() for c in row.find("td")]
                if len(cells) != 5:
                    continue
                specs = [cells[0] + " RAM", cells[1], cells[2] + " SSD", cells[3] + " transfer"]
                offers.append(record(provider, "Standard VPS " + cells[0], cells[4], specs, now, digest))
    elif provider["adapter"] == "racknerd":
        for heading in root.find("h3"):
            title = heading.text()
            if not re.fullmatch(r"[\d.]+\s*GB KVM VPS", title, re.I):
                continue
            # Find the smallest containing card with exactly one plan heading and one price.
            candidates = [n for n in root.find() if heading in list(n.find("h3"))
                          and len(list(n.find("h3"))) == 1 and re.search(r"\$\s*\d+[.\d]*\s*/\s*year", n.text(), re.I)]
            if candidates:
                complete = [n for n in candidates if any(n.find("li"))]
                node = min(complete or candidates, key=lambda n: len(n.text()))
                specs = [li.text() for li in node.find("li")]
                match = re.search(r"\$\s*\d+[.\d]*\s*/\s*year", node.text(), re.I)
                offers.append(record(provider, title, match[0], specs, now, digest))
    else:
        raise ValueError("unknown source adapter")
    if not offers or len({o["id"] for o in offers}) != len(offers):
        raise ValueError("source format changed or no unique plans parsed")
    return offers

def fetch(url):
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain"}), timeout=25) as response:
                if urlparse(response.url).scheme != "https":
                    raise ValueError("non-HTTPS redirect")
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("source exceeds byte limit")
                return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace"), raw
        except HTTPError as error:
            if error.code < 500 or attempt:
                raise
        except (URLError, TimeoutError):
            if attempt:
                raise
        time.sleep(2)
    raise RuntimeError("fetch failed")

def robots_allowed(url):
    parts = urlparse(url)
    robots_url = parts.scheme + "://" + parts.netloc + "/robots.txt"
    try:
        content, _ = fetch(robots_url)
    except HTTPError as error:
        if error.code == 404:
            return True
        raise
    parser = RobotFileParser(robots_url)
    parser.parse(content.splitlines())
    return parser.can_fetch(UA, url)

def refresh(config, previous, now, loader=fetch, robots=robots_allowed):
    results, states = [], []
    old = {o["id"]: o for o in previous.get("offers", [])}
    for provider in config["providers"]:
        state = {"provider_id": provider["id"], "source_url": provider["source_url"], "attempted_at": now}
        try:
            if not robots(provider["source_url"]):
                raise ValueError("robots.txt disallows this path")
            html, raw = loader(provider["source_url"])
            digest = hashlib.sha256(raw).hexdigest()
            fresh = parse(provider, html, now, digest)
            for offer in fresh:
                offer["first_seen_at"] = old.get(offer["id"], offer)["first_seen_at"]
            # Missing offers are removed from the active snapshot; Git retains prior evidence.
            results.extend(fresh)
            state.update(status="ok", offer_count=len(fresh), source_sha256=digest, last_success_at=now)
        except Exception as error:
            state.update(status="error", error=f"{type(error).__name__}: {error}", offer_count=0)
            for existing in old.values():
                if existing["provider_id"] == provider["id"]:
                    offer = dict(existing)
                    offer["status"] = "stale"
                    results.append(offer)
        states.append(state)
    return {"schema_version": 1, "generated_at": now, "sources": states, "offers": sorted(results, key=lambda o:o["id"])}

def main():
    config = json.loads((ROOT / "config.json").read_text("utf-8"))
    path = ROOT / "data/offers.json"
    previous = json.loads(path.read_text("utf-8")) if path.exists() else {}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result = refresh(config, previous, now)
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    tmp.replace(path)
    for state in result["sources"]:
        print(state["provider_id"], state["status"], state.get("offer_count"), state.get("error", ""))
    return 0 if any(s["status"] == "ok" for s in result["sources"]) else 2

if __name__ == "__main__":
    raise SystemExit(main())
