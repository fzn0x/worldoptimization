#!/usr/bin/env python3
"""Build an offline-browsable backup of a crawled static site.

Input is the crawl zip produced in the browser: manifest.json plus files/NNNNN
(one entry per fetched URL, bytes exactly as served). Output is the site laid
out with the server's paths, with every same-origin reference in HTML and CSS
rewritten to a relative path, so the copy works from file://, from a sub-path
(e.g. a GitHub Pages project site) or from the root of any static host.

Usage: python3 -I build_backup.py CRAWL_ZIP OUT_DIR
"""
import hashlib
import html
import json
import os
import posixpath
import re
import sys
import zipfile
from urllib.parse import quote, unquote, urljoin, urlsplit

ZIP_PATH, OUT_DIR = sys.argv[1], sys.argv[2]

zf = zipfile.ZipFile(ZIP_PATH)
meta = json.loads(zf.read("manifest.json").decode("utf-8"))
SOURCE = meta["source"]
HOST = urlsplit(SOURCE).netloc.lower()

# ---------------------------------------------------------------- path mapping
WIN_BAD = set('<>:"|?*\\%')
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def esc(ch):
    return "".join(f"%{b:02X}" for b in ch.encode("utf-8"))


def safe_segment(seg):
    """Make one decoded path segment safe on Windows/macOS/Linux (injective)."""
    s = "".join(esc(c) if (c in WIN_BAD or ord(c) < 32) else c for c in seg)
    if s and s[-1] in ". ":
        s = s[:-1] + esc(s[-1])
    if s.split(".")[0].upper() in WIN_RESERVED:
        s = esc(s[0]) + s[1:]
    return s or "%5F"


HTML_EXT = re.compile(r"\.(x?html?)$", re.I)


def local_segments(url, ctype):
    path = urlsplit(url).path or "/"
    is_dir = path.endswith("/")
    segs = [unquote(s) for s in path.split("/")[1:]]
    if is_dir:
        segs = segs[:-1]
    if ctype == "text/html":
        if is_dir or not segs or not HTML_EXT.search(segs[-1]):
            segs.append("index.html")
    elif is_dir or not segs:
        segs.append("index")
    return [safe_segment(s) for s in segs]


def lookup_key(url):
    p = unquote(urlsplit(url).path or "/")
    return p.rstrip("/") or "/"


items = [it for it in meta["items"] if it["status"] == 200]
items.sort(key=lambda it: it["url"])

# Resolve case-insensitive collisions (macOS/Windows checkouts) segment by segment.
seen = {}           # lowercased actual prefix -> actual prefix
by_key = {}         # decoded URL path (no trailing slash) -> local relpath
local_of = {}       # manifest index -> local relpath
dupes = []
for it in items:
    segs = local_segments(it["url"], it["contentType"])
    actual = []
    for seg in segs:
        cand = "/".join(actual + [seg])
        low = cand.lower()
        if low in seen and seen[low] != cand:
            seg = f"{seg}~{hashlib.sha1(seg.encode()).hexdigest()[:6]}"
            cand = "/".join(actual + [seg])
            low = cand.lower()
        seen[low] = cand
        actual.append(seg)
    rel = "/".join(actual)
    if rel in local_of.values():
        dupes.append((it["url"], rel))
        continue
    local_of[it["i"]] = rel
    for u in {it["url"], it.get("finalUrl") or it["url"]}:
        if urlsplit(u).netloc.lower() == HOST:
            by_key.setdefault(lookup_key(u), rel)

# --------------------------------------------------------------- URL rewriting
stats = {"rewritten": 0, "external": 0, "unresolved": {}, "kept_meta": 0}
SAFE = "-._~!$()*+,;=@"


def to_relative(target_rel, from_rel):
    rel = posixpath.relpath(target_rel, posixpath.dirname(from_rel) or ".")
    return "/".join(quote(seg, safe=SAFE) for seg in rel.split("/"))


def rewrite_url(raw, base_url, from_rel):
    """Return the new URL string, or None to leave the value untouched."""
    val = raw.strip()
    if not val or val.startswith(("#", "data:", "javascript:", "mailto:", "tel:", "about:", "blob:")):
        return None
    try:
        absu = urljoin(base_url, val)
        sp = urlsplit(absu)
    except ValueError:
        return None
    if sp.scheme not in ("http", "https") or sp.netloc.lower() != HOST:
        stats["external"] += 1
        return None
    target = by_key.get(lookup_key(absu))
    if target is None:
        stats["unresolved"][unquote(sp.path)] = stats["unresolved"].get(unquote(sp.path), 0) + 1
        if not re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*:|/)", val):
            return None  # document-relative (e.g. <base href=".">): still correct locally
        # Root-relative/absolute same-site URL that is not in the backup (404 on the
        # live site too): point at the original absolute URL so the intent is kept.
        return absu if val != absu else None
    stats["rewritten"] += 1
    new = to_relative(target, from_rel)
    if sp.query:
        new += "?" + sp.query
    if sp.fragment:
        new += "#" + sp.fragment
    return new


CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<u>[^'")]*)(?P=q)\s*\)""")
CSS_IMPORT = re.compile(r"""@import\s+(?P<q>['"])(?P<u>[^'"]+)(?P=q)""")


def rewrite_css(text, base_url, from_rel):
    def sub(m):
        new = rewrite_url(m.group("u"), base_url, from_rel)
        if new is None:
            return m.group(0)
        q = m.group("q") or "'"
        return m.group(0).replace(m.group("q") + m.group("u") + m.group("q"), q + new + q, 1)
    return CSS_IMPORT.sub(sub, CSS_URL.sub(sub, text))


TOKEN = re.compile(
    r"""<!--.*?-->|<!\[CDATA\[.*?\]\]>|<![^>]*>|<\?[^>]*>"""
    r"""|<(?P<name>[a-zA-Z][^\s/>]*)(?P<attrs>(?:[\s/]+[^\s"'>/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?)*)[\s/]*>""",
    re.S,
)
ATTR = re.compile(r"""(?P<lead>[\s/]*)(?P<n>[^\s"'>/=]+)(?:(?P<eq>\s*=\s*)(?P<v>"[^"]*"|'[^']*'|[^\s"'=<>`]+))?""", re.S)
URL_ATTRS = {"href", "src", "poster", "data", "action", "background", "formaction", "cite", "longdesc", "manifest"}
SRCSET_ATTRS = {"srcset", "imagesrcset"}
KEEP_LINK_RELS = {"canonical", "alternate", "shortlink"}


def attr_quote(value, q):
    value = value.replace("&", "&amp;")
    return q + (value.replace('"', "&quot;") if q == '"' else value.replace("'", "&#39;")) + q


def rewrite_attrs(tag, attrs, base_url, from_rel):
    parsed = [(m, m.group("n").lower()) for m in ATTR.finditer(attrs)]
    rels = set()
    for m, n in parsed:
        if n == "rel" and m.group("v"):
            rels |= set(html.unescape(m.group("v").strip("\"'")).lower().split())
    out, last = [], 0
    for m, n in parsed:
        v = m.group("v")
        if v is None:
            continue
        q = v[0] if v[0] in "\"'" else '"'
        raw = html.unescape(v[1:-1] if v[0] in "\"'" else v)
        new = None
        if n in URL_ATTRS:
            if tag == "link" and n == "href" and rels & KEEP_LINK_RELS:
                stats["kept_meta"] += 1
            else:
                new = rewrite_url(raw, base_url, from_rel)
        elif n in SRCSET_ATTRS:
            parts, changed = [], False
            for cand in raw.split(","):
                bits = cand.strip().split(None, 1)
                if not bits:
                    continue
                nu = rewrite_url(bits[0], base_url, from_rel)
                if nu is not None:
                    changed = True
                    bits[0] = nu
                parts.append(" ".join(bits))
            new = ", ".join(parts) if changed else None
        elif n == "style":
            nv = rewrite_css(raw, base_url, from_rel)
            new = nv if nv != raw else None
        if new is not None:
            out.append(attrs[last:m.start("v")])
            out.append(attr_quote(new, q))
            last = m.end("v")
    out.append(attrs[last:])
    return "".join(out)


def rewrite_html(text, base_url, from_rel):
    out, pos = [], 0
    while True:
        m = TOKEN.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        name = m.group("name")
        if name is None:
            out.append(m.group(0))
            pos = m.end()
            continue
        tag = name.lower()
        a0, a1 = m.start("attrs") - m.start(), m.end("attrs") - m.start()
        tok = m.group(0)
        out.append(tok[:a0] + rewrite_attrs(tag, m.group("attrs") or "", base_url, from_rel) + tok[a1:])
        pos = m.end()
        if tag in ("script", "style") and not tok.rstrip(">").rstrip().endswith("/"):
            end = re.compile(rf"</{tag}\s*>", re.I).search(text, pos)
            stop = end.start() if end else len(text)
            body = text[pos:stop]
            out.append(rewrite_css(body, base_url, from_rel) if tag == "style" else body)
            pos = stop
    return "".join(out)


# ----------------------------------------------------------------------- build
os.makedirs(OUT_DIR, exist_ok=True)
manifest_out = []
by_index = {it["i"]: it for it in items}
for idx, rel in sorted(local_of.items(), key=lambda kv: kv[1]):
    it = by_index[idx]
    data = zf.read(it["file"])
    assert len(data) == it["size"], (it["url"], len(data), it["size"])
    base_url = it.get("finalUrl") or it["url"]
    if it["contentType"] in ("text/html", "text/css"):
        text = data.decode("utf-8", errors="surrogateescape")
        if it["contentType"] == "text/html":
            text = rewrite_html(text, base_url, rel)
        else:
            text = rewrite_css(text, base_url, rel)
        out_bytes = text.encode("utf-8", errors="surrogateescape")
    else:
        out_bytes = data
    dest = os.path.join(OUT_DIR, *rel.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(out_bytes)
    manifest_out.append({
        "url": it["url"],
        "path": rel,
        "contentType": it["contentType"],
        "bytes": it["size"],
        "sha256": hashlib.sha256(data).hexdigest(),
        "lastModified": it.get("lastModified") or None,
        **({"servedAt": it["finalUrl"]} if it.get("redirected") else {}),
    })

os.makedirs(os.path.join(OUT_DIR, "_backup"), exist_ok=True)
with open(os.path.join(OUT_DIR, "_backup", "manifest.json"), "w", encoding="utf-8") as fh:
    json.dump({
        "source": SOURCE,
        "crawledAt": meta["crawledAt"],
        "note": "sha256/bytes are of the files exactly as served; HTML/CSS in this repo have same-site links rewritten to relative paths.",
        "files": manifest_out,
        "missingOnLiveSite": [{"url": e["url"], "status": e["status"]} for e in meta["errors"]],
        "externalAssetHosts": meta.get("externalAssetHosts", []),
    }, fh, indent=1, ensure_ascii=False)

summary = {
    "files": len(manifest_out),
    "html": sum(1 for f in manifest_out if f["contentType"] == "text/html"),
    "bytes": sum(f["bytes"] for f in manifest_out),
    "duplicates_skipped": dupes,
    "renamed_for_case_collisions": sorted(p for p in local_of.values() if "~" in p and re.search(r"~[0-9a-f]{6}(/|$)", p)),
    "escaped_paths": sorted(p for p in local_of.values() if "%" in p),
    "refs_rewritten": stats["rewritten"],
    "refs_external_left": stats["external"],
    "link_rel_kept": stats["kept_meta"],
    "same_site_refs_not_in_backup": stats["unresolved"],
}
print(json.dumps(summary, indent=1, ensure_ascii=False))
