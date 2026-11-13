# worldoptimization — offline backup of worldoptimization.k55.io

A complete copy of **https://worldoptimization.k55.io/**, the archive site of the Tumblr blog
*Fake Charity Nerd Girl* (`worldoptimization`), with both its design and its content: the stylesheet,
the scripts (including the light/dark theme switcher and j/k post navigation), every image and every page.

| | |
|---|---|
| Crawled | 2026-11-13 19:37 UTC |
| Pages | 1,120 HTML files: the home page (all 833 posts), 833 post pages, 282 tag pages and 4 saved tweet-embed pages |
| Assets | 213 files: 1 stylesheet, 6 scripts, 206 images (every image the site uses is hosted on the site itself) |
| Size | 15.1 MB |

## Browsing it

- **From disk:** open `index.html` in a browser. Everything works without a network connection.
- **Local server:** run `python3 -m http.server` in this folder and open http://localhost:8000/.
- **GitHub Pages:** Settings → Pages → *Deploy from a branch* → `main`, `/ (root)`. A `.nojekyll` file is
  included so the `_astro/` stylesheet folder is served. The pages keep the original
  `<meta name="robots" content="noindex">`.

## What is (and isn't) changed

- Files keep the site's own layout: `/post/<id>/<slug>` is `post/<id>/<slug>/index.html`, and
  `/tagged/<tag>` is `tagged/<tag>/index.html`.
- The only edits are to same-site links in the HTML (`href`, `src`, `srcset`): root-relative links such as
  `/tagged/goodreads` became relative links such as `../../tagged/goodreads/index.html`, so the copy works
  from disk and from any sub-path. Images, scripts and the stylesheet are byte-identical to what the
  site served, and page text and markup are otherwise untouched.
- Nine tag names contain `:`, which Windows can't use in file names, so their folders spell it `%3A`
  (for example `tagged/epistemic status%3A only kind of serious/`). Links point to those folders.
- [`_backup/manifest.json`](_backup/manifest.json) lists every original URL with its path here, content type,
  size, `Last-Modified` header and the SHA-256 of the bytes as served.

## Known gaps (same on the live site)

- 11 tag pages whose names contain `?` (such as `#maybe?` and `#???`) return 404 on worldoptimization.k55.io
  itself, so they couldn't be saved. Links to them still point at the original URLs.
- Links to other sites (Goodreads, other Tumblr blogs, Wikipedia and so on) stay external links.
- The two embedded tweets are saved pages from the original archive. Online, they also load a few files
  from Twitter's servers (its fonts, two profile pictures and its widget script). Offline they look the
  same as on the live site; the browser console just reports the Twitter requests that can't be made.

## Refreshing the backup

1. Open https://worldoptimization.k55.io/ in a browser, paste [`_backup/tools/crawl.js`](_backup/tools/crawl.js)
   into the DevTools console and press Enter. It downloads `worldoptimization-k55-crawl.zip`.
2. Build into an empty folder: `python3 _backup/tools/build_backup.py worldoptimization-k55-crawl.zip new-copy`.
3. Check it: `python3 _backup/tools/check_links.py new-copy worldoptimization-k55-crawl.zip`.
   Every same-site link should resolve, apart from the 404 tag pages listed above.
4. Replace this folder's contents with `new-copy` (keep `.git`, `README.md`, `.nojekyll`, `.gitattributes`
   and `_backup/tools/`), then commit.
