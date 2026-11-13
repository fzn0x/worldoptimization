/*
 * Browser-side crawler used to make this backup of https://worldoptimization.k55.io/
 *
 * Open the site's home page, paste this whole file into the DevTools console
 * and press Enter. It fetches every same-origin page and asset (following
 * links, stylesheets, scripts, images and iframes) with the browser's own
 * network stack, then downloads <host>-crawl.zip: manifest.json plus
 * files/NNNNN holding the bytes exactly as served.
 *
 * Turn the zip into the browsable copy with:
 *     python3 build_backup.py <host>-crawl.zip <output-dir>
 */
(async () => {
  const DOWNLOAD = true; // false = crawl and report counts only
  const CONCURRENCY = 6;

  const ORIGIN = location.origin;
  const items = new Map(), queued = new Set(), queue = [], errors = [], external = new Map();
  let inFlight = 0;

  const norm = (u, base) => {
    if (u == null) return null;
    u = String(u).trim();
    if (!u || /^(data|javascript|mailto):/.test(u) || u.startsWith('#')) return null;
    try { const x = new URL(u, base); if (!/^https?:$/.test(x.protocol)) return null; x.hash = ''; return x; } catch (e) { return null; }
  };
  const enqueue = (u, base, isAsset) => {
    const x = norm(u, base);
    if (!x) return;
    if (x.origin !== ORIGIN) { if (isAsset) external.set(x.host, (external.get(x.host) || 0) + 1); return; }
    if (queued.has(x.href)) return;
    queued.add(x.href);
    queue.push(x.href);
  };
  const cssUrls = (text, base) => {
    let m; const re = /url\(\s*(['"]?)([^'")]+)\1\s*\)/g;
    while ((m = re.exec(text))) enqueue(m[2], base, true);
    const re2 = /@import\s+(['"])([^'"]+)\1/g;
    while ((m = re2.exec(text))) enqueue(m[2], base, true);
  };
  const srcset = (v, base) => (v || '').split(',').forEach(p => { const u = p.trim().split(/\s+/)[0]; if (u) enqueue(u, base, true); });
  const parseHtml = (text, base) => {
    const doc = new DOMParser().parseFromString(text, 'text/html');
    const b = doc.querySelector('base[href]'); if (b) base = new URL(b.getAttribute('href'), base).href;
    doc.querySelectorAll('a[href], area[href]').forEach(a => enqueue(a.getAttribute('href'), base, false));
    doc.querySelectorAll('link[href]').forEach(l => enqueue(l.getAttribute('href'), base, true));
    doc.querySelectorAll('script[src], img[src], source[src], video[src], audio[src], track[src], iframe[src], embed[src], input[src]').forEach(e => enqueue(e.getAttribute('src'), base, true));
    doc.querySelectorAll('video[poster]').forEach(e => enqueue(e.getAttribute('poster'), base, true));
    doc.querySelectorAll('object[data]').forEach(e => enqueue(e.getAttribute('data'), base, true));
    doc.querySelectorAll('img[srcset], source[srcset]').forEach(e => srcset(e.getAttribute('srcset'), base));
    doc.querySelectorAll('[style]').forEach(e => cssUrls(e.getAttribute('style'), base));
    doc.querySelectorAll('style').forEach(s => cssUrls(s.textContent, base));
    doc.querySelectorAll('meta[content]').forEach(m => { const c = m.getAttribute('content') || ''; if (/^(https?:)?\/\//.test(c) || c.startsWith('/')) { const x = norm(c, base); if (x && x.origin === ORIGIN) enqueue(c, base, true); } });
  };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const worker = async () => {
    for (;;) {
      const key = queue.shift();
      if (!key) { if (inFlight === 0) return; await sleep(150); continue; }
      inFlight++;
      try {
        let r = null;
        for (let tries = 0; tries < 4; tries++) {
          try { r = await fetch(key, { credentials: 'omit', cache: 'no-cache', redirect: 'follow' }); } catch (e) { r = null; }
          if (r && r.status < 500 && r.status !== 429) break;
          await sleep(1000 * (tries + 1));
        }
        if (!r) { errors.push([key, 'network']); continue; }
        const ct = (r.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
        const buf = await r.arrayBuffer();
        items.set(key, { url: key, status: r.status, ct, finalUrl: r.url, redirected: r.redirected, size: buf.byteLength, lastModified: r.headers.get('last-modified') || '', buf });
        if (r.status >= 400) errors.push([key, r.status]);
        if (r.url && r.url !== key) queued.add(r.url);
        if (r.status < 400) {
          if (ct === 'text/html') parseHtml(new TextDecoder().decode(buf), r.url || key);
          else if (ct === 'text/css') cssUrls(new TextDecoder().decode(buf), r.url || key);
        }
      } catch (e) { errors.push([key, String(e)]); }
      finally { inFlight--; }
    }
  };

  enqueue('/', location.href, false);
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));

  // ---- zip (DEFLATE via CompressionStream, plain zip, no zip64) ----
  const crcT = new Uint32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc32 = u8 => { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = crcT[(c ^ u8[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  const deflate = async u8 => new Uint8Array(await new Response(new Blob([u8]).stream().pipeThrough(new CompressionStream('deflate-raw'))).arrayBuffer());
  const now = new Date();
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
  const entries = [], manifest = [];
  let i = 0;
  for (const it of items.values()) {
    const name = 'files/' + String(i).padStart(5, '0');
    manifest.push({ i, file: name, url: it.url, finalUrl: it.finalUrl, status: it.status, contentType: it.ct, redirected: it.redirected, size: it.size, lastModified: it.lastModified });
    entries.push({ name, raw: new Uint8Array(it.buf) });
    i++;
  }
  const meta = { source: ORIGIN + '/', crawledAt: now.toISOString(), userAgent: navigator.userAgent, errors: errors.map(e => ({ url: e[0], status: e[1] })), externalAssetHosts: [...external.entries()], items: manifest };
  entries.unshift({ name: 'manifest.json', raw: new TextEncoder().encode(JSON.stringify(meta, null, 1)) });
  const parts = [], central = [], enc = new TextEncoder();
  let off = 0;
  for (const e of entries) {
    const nb = enc.encode(e.name), crc = crc32(e.raw);
    let data = await deflate(e.raw), method = 8;
    if (data.length >= e.raw.length) { data = e.raw; method = 0; }
    const lh = new DataView(new ArrayBuffer(30));
    lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true); lh.setUint16(8, method, true);
    lh.setUint16(10, dosTime, true); lh.setUint16(12, dosDate, true); lh.setUint32(14, crc, true);
    lh.setUint32(18, data.length, true); lh.setUint32(22, e.raw.length, true); lh.setUint16(26, nb.length, true);
    parts.push(new Uint8Array(lh.buffer), nb, data);
    const ch = new DataView(new ArrayBuffer(46));
    ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true); ch.setUint16(10, method, true);
    ch.setUint16(12, dosTime, true); ch.setUint16(14, dosDate, true); ch.setUint32(16, crc, true); ch.setUint32(20, data.length, true); ch.setUint32(24, e.raw.length, true);
    ch.setUint16(28, nb.length, true); ch.setUint32(42, off, true);
    central.push(new Uint8Array(ch.buffer), nb);
    off += 30 + nb.length + data.length;
  }
  const cdSize = central.reduce((a, b) => a + b.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true); end.setUint16(10, entries.length, true); end.setUint32(12, cdSize, true); end.setUint32(16, off, true);
  const blob = new Blob([...parts, ...central, new Uint8Array(end.buffer)], { type: 'application/zip' });

  const vals = [...items.values()];
  const summary = {
    fetched: items.size,
    html: vals.filter(v => v.ct === 'text/html' && v.status === 200).length,
    assets: vals.filter(v => v.ct !== 'text/html' && v.status === 200).length,
    notFound: errors.length,
    zipBytes: blob.size,
  };
  if (DOWNLOAD) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = location.host.split('.')[0] + '-' + location.host.split('.').slice(-2, -1)[0] + '-crawl.zip';
    document.body.appendChild(a); a.click(); a.remove();
  }
  console.log('crawl summary', summary);
  return summary;
})();
