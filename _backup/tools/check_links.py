#!/usr/bin/env python3
"""Static check of the built backup: every same-site reference must resolve to a
file inside the backup, and binary assets must be byte-identical to the crawl.

Usage: python3 -I check_links.py SITE_DIR CRAWL_ZIP
"""
import collections
import hashlib
import html
import json
import os
import re
import sys
import zipfile
from urllib.parse import unquote, urlsplit

SITE, ZIP = sys.argv[1], sys.argv[2]
zf = zipfile.ZipFile(ZIP)
meta = json.loads(zf.read("manifest.json"))
HOST = urlsplit(meta["source"]).netloc

ATTR = re.compile(r"""\s(href|src|poster|data|srcset|action)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""", re.I)
CSSURL = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""")
SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.S | re.I)

problems = collections.defaultdict(list)
counts = collections.Counter()


def check_ref(val, src_rel, kind):
    val = html.unescape(val).strip()
    if not val or val.startswith(("#", "data:", "javascript:", "mailto:", "tel:", "about:", "blob:")):
        return
    sp = urlsplit(val)
    if sp.scheme in ("http", "https") or val.startswith("//"):
        if sp.netloc == HOST:
            counts["absolute_same_site"] += 1
            problems["absolute_same_site"].append((src_rel, unquote(sp.path)))
        else:
            counts["external"] += 1
        return
    if sp.scheme:
        counts["other_scheme"] += 1
        return
    if val.startswith("/"):
        counts["root_relative"] += 1
        problems["root_relative"].append((src_rel, val))
        return
    target = os.path.normpath(os.path.join(SITE, os.path.dirname(src_rel), unquote(sp.path)))
    if not target.startswith(os.path.abspath(SITE)):
        problems["escapes_site"].append((src_rel, val))
        return
    if os.path.isdir(target):
        counts["dir_ref"] += 1
        problems["dir_ref"].append((src_rel, val))
        return
    if os.path.isfile(target):
        counts["local_ok_" + kind] += 1
    else:
        counts["local_missing"] += 1
        problems["local_missing"].append((src_rel, val))


files = []
for root, dirs, names in os.walk(SITE):
    dirs[:] = [d for d in dirs if d != ".git"]
    for n in names:
        files.append(os.path.relpath(os.path.join(root, n), SITE).replace(os.sep, "/"))

for rel in files:
    p = os.path.join(SITE, rel)
    if rel.endswith(".html"):
        text = open(p, encoding="utf-8", errors="surrogateescape").read()
        # base href="." pages resolve relative to themselves, which is what we do anyway
        for m in SCRIPT_STYLE.finditer(text):
            if m.group(1).lower() == "style":
                for u in CSSURL.findall(m.group(0)):
                    check_ref(u, rel, "css")
        stripped = SCRIPT_STYLE.sub(lambda m: re.match(r"<[^>]*>", m.group(0)).group(0), text)
        for m in ATTR.finditer(stripped):
            name = m.group(1).lower()
            val = next(g for g in m.groups()[2:] if g is not None)
            if name == "srcset":
                for cand in val.split(","):
                    bits = cand.strip().split()
                    if bits:
                        check_ref(bits[0], rel, "srcset")
            else:
                check_ref(val, rel, name)
        for m in re.finditer(r"""style\s*=\s*("([^"]*)"|'([^']*)')""", stripped):
            for u in CSSURL.findall(html.unescape(m.group(2) or m.group(3) or "")):
                check_ref(u, rel, "style")
    elif rel.endswith(".css"):
        for u in CSSURL.findall(open(p, encoding="utf-8").read()):
            check_ref(u, rel, "css")

# Byte-identity of non-HTML/CSS assets, and file-set completeness
man = json.load(open(os.path.join(SITE, "_backup", "manifest.json")))
mismatch, missing = [], []
for f in man["files"]:
    p = os.path.join(SITE, *f["path"].split("/"))
    if not os.path.isfile(p):
        missing.append(f["path"])
        continue
    if f["contentType"] not in ("text/html", "text/css"):
        if hashlib.sha256(open(p, "rb").read()).hexdigest() != f["sha256"]:
            mismatch.append(f["path"])
crawl_ok = sum(1 for i in meta["items"] if i["status"] == 200)

print(json.dumps({
    "files_on_disk": len(files),
    "crawl_200_urls": crawl_ok,
    "manifest_files": len(man["files"]),
    "manifest_files_missing_on_disk": missing[:10],
    "binary_assets_not_identical": mismatch[:10],
    "counts": counts,
    "problems": {k: (len(v), sorted(set(x[1] for x in v))[:15]) for k, v in problems.items()},
}, indent=1, ensure_ascii=False, default=dict))
