"""Deterministic static rendering; no network, dependencies, keys or inference."""
import json
import os
import re
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site"

def e(value):
    return escape(str(value), quote=True)

def https(url):
    p = urlparse(url)
    if p.scheme != "https" or not p.netloc or p.username or p.password:
        raise ValueError("Only public HTTPS URLs are allowed")
    return url

def template(filename, **values):
    return Template((ROOT / "templates" / filename).read_text("utf-8")).substitute(values)

def classify(offer, now, hours):
    if offer.get("valid_until") and datetime.fromisoformat(offer["valid_until"]) <= now:
        return "expired"
    age = (now - datetime.fromisoformat(offer["checked_at"])).total_seconds()/3600
    return "stale" if offer["status"] != "observed" or age > hours else "observed"

def main():
    config = json.loads((ROOT / "config.json").read_text("utf-8"))
    data = json.loads((ROOT / "data/offers.json").read_text("utf-8"))
    now = datetime.now(timezone.utc)
    providers = {p["id"]:p for p in config["providers"]}
    origin = config.get("base_url") or os.environ.get("CF_PAGES_URL", "")
    origin = https(origin).rstrip("/") if origin else ""
    if OUT.exists():
        if OUT.resolve() != ROOT.resolve() / "site":
            raise ValueError("invalid output path")
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "static", OUT / "assets")
    routes = []
    def page(path, title, description, body):
        target = OUT / path / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        route = "/" + path.strip("/") + "/" if path else "/"
        canonical = f'<link rel="canonical" href="{e(origin+route)}">' if origin else ""
        target.write_text(template("layout.html", title=e(title), description=e(description),
                                  brand=e(config["brand"]), body=body, canonical=canonical,
                                  repository=e(https(config["repository"])), updated=e(data["generated_at"])), "utf-8")
        routes.append(route)
    offers = data["offers"]
    for offer in offers:
        if not re.fullmatch(r"[a-z0-9-]+", offer["id"]) or offer["provider_id"] not in providers:
            raise ValueError("invalid offer identifier")
        if offer["billing_period"] not in {"month", "year"} or offer["currency"] != "USD" or Decimal(offer["price"]) <= 0:
            raise ValueError("invalid price")
        https(offer["source_url"])
        offer["display_status"] = classify(offer, now, config["stale_after_hours"])
    offers.sort(key=lambda o:(o["display_status"] != "observed", Decimal(o["price"])/(12 if o["billing_period"] == "year" else 1), o["id"]))
    status_names = {"observed":"已读取官方标价", "stale":"旧记录 · 待核验", "expired":"已过期"}
    def money(o):
        return "US$" + e(o["price"]) + (" / 年" if o["billing_period"] == "year" else " / 月")
    def cards(items):
        parts = []
        for o in items:
            p = providers[o["provider_id"]]
            kind = "官方促销" if o["kind"] == "promotion" else "常规定价"
            specs = " · ".join(e(s) for s in o["specs"][:4])
            parts.append(f'<article class="deal" data-checked="{e(o["checked_at"])}"><div class="deal-top"><a class="provider" href="/providers/{e(p["id"])}/">{e(p["name"])}</a><span class="tag">{kind}</span></div><h3><a href="/deals/{e(o["id"])}/">{e(o["title"])}</a></h3><p class="price">{money(o)}</p><p class="specs">{specs}</p><div class="deal-bottom"><span class="status {e(o["display_status"])}">{status_names[o["display_status"]]}</span><a aria-label="查看 {e(p["name"])} {e(o["title"])} 详情" href="/deals/{e(o["id"])}/">详情 ↗</a></div></article>')
        return '<div class="deals">' + "".join(parts) + '</div>' if parts else '<p class="empty">本次没有可展示的已核验套餐。请查看下方官方来源与采集状态。</p>'
    states = {s["provider_id"]:s for s in data["sources"]}
    source_rows = ""
    for p in providers.values():
        s = states[p["id"]]
        label = f'成功 · {s["offer_count"]} 条记录' if s["status"] == "ok" else '读取失败 · 未发布新价格'
        source_rows += f'<tr><th><a href="/providers/{e(p["id"])}/">{e(p["name"])}</a></th><td><a href="{e(p["source_url"])}" rel="noopener noreferrer">官方来源 ↗</a></td><td>{label}</td></tr>'
        own = [o for o in offers if o["provider_id"] == p["id"]]
        page("providers/"+p["id"], p["name"]+" VPS 价格与来源 | vps-deals", "官方套餐标价、来源与核验时间。",
             template("provider.html", name=e(p["name"]), homepage=e(https(p["homepage"])), source=e(p["source_url"]),
                      state=e(label), checked=e(s["attempted_at"]), cards=cards(own)))
    for o in offers:
        p = providers[o["provider_id"]]
        link = config["affiliate_links"].get(o["id"], {})
        affiliate = bool(link.get("approved") and link.get("url"))
        url = https(link["url"] if affiliate else o["offer_url"])
        specs = "".join('<li>'+e(s)+'</li>' for s in o["specs"])
        page("deals/"+o["id"], p["name"]+" "+o["title"]+" | vps-deals", "查看官方标价、计费周期和价格来源。",
             template("deal.html", provider=e(p["name"]), provider_id=e(p["id"]), title=e(o["title"]),
                      kind="官方促销" if o["kind"] == "promotion" else "常规定价 · 非优惠券", price=money(o),
                      status=status_names[o["display_status"]], checked=e(o["checked_at"]), specs=specs,
                      source=e(o["source_url"]), evidence=e(o["evidence"]), digest=e(o["source_sha256"]),
                      url=e(url), rel="sponsored noopener noreferrer" if affiliate else "noopener noreferrer",
                      disclosure="联盟链接：通过此链接购买，我们可能获得佣金。" if affiliate else "普通官方链接：当前未配置联盟追踪。"))
    count = len([o for o in offers if o["display_status"] == "observed"])
    promo = len([o for o in offers if o["display_status"] == "observed" and o["kind"] == "promotion"])
    page("", "VPS 优惠与官方价格雷达 | vps-deals", "对比有来源的 VPS 套餐标价，区分促销与常规定价，查看采集状态。",
         template("index.html", count=count, providers=len(providers), promos=promo, cards=cards(offers), source_rows=source_rows))
    rows = ""
    for o in offers:
        monthly = Decimal(o["price"])/(12 if o["billing_period"] == "year" else 1)
        rows += f'<tr><th><a href="/deals/{e(o["id"])}/">{e(providers[o["provider_id"]]["name"])} · {e(o["title"])}</a></th><td>{money(o)}</td><td>US${monthly:.2f}</td><td>{" · ".join(e(s) for s in o["specs"][:3])}</td><td>{status_names[o["display_status"]]}</td></tr>'
    page("compare", "VPS 价格对比 | vps-deals", "按官方计费周期对比 VPS 价格；年付折月仅供比较。", template("compare.html", rows=rows))
    page("about", "来源与披露 | vps-deals", "采集方法、价格边界和联盟链接披露。", template("about.html"))
    (OUT / "data").mkdir()
    (OUT / "data/offers.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", "utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {origin}/sitemap.xml\n" if origin else ""), "utf-8")
    if origin:
        (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{e(origin+r)}</loc></url>' for r in routes)+'</urlset>', "utf-8")
    (OUT / "404.html").write_text(template("layout.html", title="页面不存在 | vps-deals", description="页面不存在或套餐已移除。", brand=e(config["brand"]), body='<h1>这条记录已移除或不存在</h1><p>优惠源会变化，请返回查看最新记录。</p><a href="/">回到价格雷达</a>', canonical="", repository=e(config["repository"]), updated=e(data["generated_at"])), "utf-8")
    (OUT / "_headers").write_text("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'self'\n", "utf-8")
    print(f"Built {len(routes)} pages, {len(offers)} offers; source errors: {sum(s['status'] != 'ok' for s in states.values())}")

if __name__ == "__main__":
    main()
