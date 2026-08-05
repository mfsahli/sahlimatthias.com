#!/usr/bin/env python3
"""
Weekly publication updater for sahlimatthias.com
=================================================
Fetches current publication + citation data from the Semantic Scholar and
OpenAlex APIs (free, official, no scraping), merges it with the manually
curated fields in data/publications.json, and injects the result into
index.html. Run by GitHub Actions every Monday (see
.github/workflows/update-publications.yml) — or manually:

    python3 scripts/update_publications.py

Manual fields (finding, tags, links, status, note, short) are NEVER
overwritten. Newly discovered papers are appended with "manual": false —
add tags/finding to them in data/publications.json whenever you like.

GOOGLE SCHOLAR NUMBERS (optional, recommended):
Google blocks direct crawling of Scholar, so the true Scholar counts come in
via SerpAPI's official Google Scholar Author API (free tier: 100 requests per
month — the weekly run uses ~4-5). Setup: create an account at serpapi.com,
copy your key, add it as repository secret SERPAPI_KEY (GitHub repo →
Settings → Secrets and variables → Actions). With the key present, citation
counts, the per-year graph and per-paper Scholar links come straight from
your Scholar profile; without it, the script falls back to Semantic Scholar
and OpenAlex automatically.
"""
import json, os, re, sys, urllib.request, datetime, difflib
from pathlib import Path

# ---------------------------------------------------------------- config
S2_AUTHOR_ID = "2206113966"        # semanticscholar.org author id for Matthias Sahli
SCHOLAR_AUTHOR_ID = "ui-NYv8AAAAJ" # google scholar profile id
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
OPENALEX_QUERY = "https://api.openalex.org/authors?search=Matthias%20Sahli&per-page=25"
# Once known, pin the OpenAlex author id here (e.g. "A5023456789") for robustness:
OPENALEX_AUTHOR_ID = ""
MIN_YEAR = 2019                     # drops false matches (e.g. a 2003 antenna paper by another M. Sahli)
ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "publications.json"
INDEX_FILE = ROOT / "index.html"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "sahlimatthias.com publication updater (mailto:sahlimatthias@gmail.com)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def norm(t):
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()

def match(title, pubs):
    """Find existing entry whose title fuzzy-matches."""
    nt = norm(title)
    best, score = None, 0.0
    for p in pubs:
        s = difflib.SequenceMatcher(None, nt, norm(p["title"])).ratio()
        if s > score:
            best, score = p, s
    return best if score >= 0.55 else None

def main():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    pubs = data["publications"]
    log = []

    # ---------------- Semantic Scholar: per-paper citations + author metrics
    try:
        author = get(f"https://api.semanticscholar.org/graph/v1/author/{S2_AUTHOR_ID}"
                     "?fields=citationCount,hIndex,paperCount")
        papers = get(f"https://api.semanticscholar.org/graph/v1/author/{S2_AUTHOR_ID}/papers"
                     "?fields=title,year,venue,citationCount,externalIds&limit=200")["data"]
        papers = [p for p in papers if (p.get("year") or 0) >= MIN_YEAR]

        # aggregate duplicate S2 records (e.g. SSRN preprint + journal version) by fuzzy title
        for p in papers:
            hit = match(p["title"], pubs)
            if hit:
                hit["_s2cit"] = hit.get("_s2cit", 0) + (p.get("citationCount") or 0)
                doi = (p.get("externalIds") or {}).get("DOI")
                if doi and not any(l["label"] == "DOI" for l in hit.get("links", [])):
                    hit.setdefault("links", []).insert(0, {"label": "DOI", "url": f"https://doi.org/{doi}"})
                    log.append(f"added DOI to: {hit['id']}")
            elif not SERPAPI_KEY:
                # without a Scholar key, S2 is the discovery source for new papers
                new_id = re.sub(r"[^a-z0-9]+", "-", norm(p["title"]))[:40].strip("-")
                pubs.append({
                    "id": new_id, "title": p["title"], "authors": "M. Sahli et al.",
                    "venue": p.get("venue") or "—", "year": p.get("year"),
                    "status": "published", "tags": [], "citations": p.get("citationCount") or 0,
                    "links": [], "manual": False,
                })
                log.append(f"NEW paper discovered via S2: {p['title']}")

        for p in pubs:
            if "_s2cit" in p:
                p["citations"] = max(p.get("citations") or 0, p.pop("_s2cit"))

        data["metrics"]["citations"] = author.get("citationCount") or data["metrics"]["citations"]
        data["metrics"]["hIndex"] = author.get("hIndex") or data["metrics"]["hIndex"]
        log.append("semantic scholar: ok")
    except Exception as e:
        log.append(f"semantic scholar FAILED (kept previous data): {e}")

    # ---------------- OpenAlex: citations per year (for the year chart)
    try:
        if OPENALEX_AUTHOR_ID:
            oa = get(f"https://api.openalex.org/authors/{OPENALEX_AUTHOR_ID}")
        else:
            cands = get(OPENALEX_QUERY)["results"]
            oa = next((c for c in cands if any("Bern" in (i.get("display_name") or "") or
                                               "Neuch" in (i.get("display_name") or "") or
                                               "Intellectual Property" in (i.get("display_name") or "")
                                               for i in (c.get("last_known_institutions") or []))),
                      cands[0] if cands else None)
        if oa:
            cby = sorted([{"year": d["year"], "citations": d["cited_by_count"]}
                          for d in oa.get("counts_by_year", []) if d["year"] >= MIN_YEAR],
                         key=lambda d: d["year"])
            if cby:
                data["metrics"]["citationsByYear"] = cby
            log.append(f"openalex: ok ({oa['id']}) — pin OPENALEX_AUTHOR_ID='{oa['id'].rsplit('/',1)[-1]}'")
    except Exception as e:
        log.append(f"openalex FAILED (kept previous data): {e}")

    # ---------------- Google Scholar via SerpAPI (optional, most accurate)
    if SERPAPI_KEY:
        try:
            sp = get("https://serpapi.com/search.json?engine=google_scholar_author"
                     f"&author_id={SCHOLAR_AUTHOR_ID}&api_key={SERPAPI_KEY}&num=100&hl=en")
            arts = sp.get("articles") or []
            for a in arts:
                title = a.get("title","")
                cby = (a.get("cited_by") or {})
                cid = a.get("citation_id")
                surl = ("https://scholar.google.com/citations?view_op=view_citation"
                        f"&hl=en&user={SCHOLAR_AUTHOR_ID}&citation_for_view={cid}") if cid else None
                hit = match(title, pubs)
                if hit:
                    if isinstance(cby.get("value"), int):
                        hit["citations"] = cby["value"]           # Scholar count wins (merged versions)
                    if surl:
                        hit["scholarUrl"] = surl
                    if hit.get("status") == "working" and a.get("publication"):
                        log.append(f"HINT: '{hit['id']}' is a working paper here but Scholar lists "
                                   f"“{a['publication']}” — published now? Update status/venue in data/publications.json.")
                else:
                    # your Scholar profile is curated by you → new entries there are auto-added as published
                    new_id = re.sub(r"[^a-z0-9]+", "-", norm(title))[:40].strip("-") or "untitled"
                    year = a.get("year")
                    pubs.append({
                        "id": new_id, "title": title,
                        "authors": a.get("authors") or "M. Sahli et al.",
                        "venue": a.get("publication") or "—",
                        "year": int(year) if str(year).isdigit() else None,
                        "status": "published", "tags": [],
                        "citations": cby.get("value") or 0,
                        "links": [], "manual": False,
                        **({"scholarUrl": surl} if surl else {}),
                    })
                    log.append(f"NEW paper auto-added from your Scholar profile: {title} "
                               "(add tags/finding in data/publications.json when you like)")
            ct = sp.get("cited_by", {}).get("table", [])
            for row in ct:
                if "citations" in row: data["metrics"]["citations"] = row["citations"].get("all", data["metrics"]["citations"])
                if "h_index"  in row: data["metrics"]["hIndex"]   = row["h_index"].get("all", data["metrics"]["hIndex"])
            graph = sp.get("cited_by", {}).get("graph", [])
            if graph:
                data["metrics"]["citationsByYear"] = [{"year": g["year"], "citations": g.get("citations", 0)} for g in graph]
                data["metrics"]["yearSourceLabel"] = "Google Scholar"
            data["metrics"]["sourceLabel"] = "Google Scholar"
            log.append(f"google scholar via serpapi: ok ({len(arts)} articles)")
        except Exception as e:
            log.append(f"serpapi FAILED (kept API fallback data): {e}")
    else:
        log.append("no SERPAPI_KEY set — using Semantic Scholar/OpenAlex numbers")

    # ---------------- recompute derived metrics
    data["metrics"]["publications"] = len(pubs)
    data["metrics"]["venues"] = len({p["venue"] for p in pubs if p.get("status") == "published"})
    data["generated"] = datetime.date.today().isoformat()

    # ---------------- write data file
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- inject into index.html
    html = INDEX_FILE.read_text(encoding="utf-8")
    new_html, n = re.subn(
        r'(<script id="site-data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + "\n" + json.dumps(data, ensure_ascii=False) + "\n" + m.group(2),
        html, count=1, flags=re.S)
    if n != 1:
        print("ERROR: site-data block not found in index.html"); sys.exit(1)
    INDEX_FILE.write_text(new_html, encoding="utf-8")

    print("\n".join(log))
    print(f"OK — {len(pubs)} publications, {data['metrics']['citations']} citations, generated {data['generated']}")

if __name__ == "__main__":
    main()
