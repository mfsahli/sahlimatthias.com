#!/usr/bin/env python3
"""
CV builder for sahlimatthias.com
================================
Merges the auto-updated publication data (data/publications.json, mirrored from
Google Scholar by scripts/update_publications.py) with the manually maintained
CV content (pdf/cv.json), renders pdf/cv_template.html and prints it with
headless Chromium — so the PDFs carry exactly the website's typography and
colours.

Produces two files in one run:
    cv.pdf        full academic CV
    cv_short.pdf  the essentials, 1-2 pages

Run it whenever you want a fresh CV:

    python3 pdf/build_cv.py

Requires: pip install playwright  &&  playwright install chromium
"""
import json, sys, datetime, html, base64, urllib.request
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
# Publication data: pulled live from the website (always the latest Scholar
# mirror written by the weekly workflow); falls back to a local copy offline.
PUBS_URL = "https://sahlimatthias.com/data/publications.json"
PUBS  = ROOT / "data" / "publications.json"
CV    = ROOT / "pdf"  / "cv.json"
TPL   = ROOT / "pdf"  / "cv_template.html"
PHOTO = ROOT / "pdf"  / "photo.png"
OUT_FULL  = ROOT / "cv.pdf"
OUT_SHORT = ROOT / "cv_short.pdf"

DOTS = ["var(--red)", "var(--ochre)", "var(--green)", "var(--blue)", "var(--purple)"]

def e(s):
    return html.escape(str(s or ""))

# ---------------------------------------------------------------- pieces
def rows(items, year_key, main):
    out = ['<div class="rows">']
    for it in items:
        out.append(f'<div class="yr">{e(it.get(year_key,""))}</div>'
                   f'<div class="it">{main(it)}</div>')
    out.append("</div>")
    return "".join(out)

def org_row(it):
    s = f'<b>{e(it["org"])}</b>'
    if it.get("place"): s += f' <span>&middot; {e(it["place"])}</span>'
    if it.get("role"):  s += f'<br><span>{e(it["role"])}</span>'
    return s

def teach_row(it):
    s = f'<b>{e(it["org"])}</b><br><span>{e(it["role"])}</span>'
    if it.get("eval"): s += f'<br><span class="eval">&#9733; {e(it["eval"])}</span>'
    return s

PUB_GROUPS = [
    ("published", "Peer-reviewed publications"),
    ("review",    "Under review"),
    ("progress",  "Work in progress"),
    ("other",     "Book chapters, dissertation &amp; other output"),
]
BADGE_COLOR = {"review": "var(--ochre)", "progress": "var(--purple)", "other": "var(--ink3)"}

def publications_block(pubs, only=None):
    out = []
    for key, label in PUB_GROUPS:
        if only and key not in only:
            continue
        group = sorted([p for p in pubs if p.get("status") == key and not p.get("hidden")],
                       key=lambda p: (p.get("year") or 0), reverse=True)
        if not group:
            continue
        out.append(f'<div class="pgroup">{label}</div>')
        for p in group:
            badge, col = "", BADGE_COLOR.get(key)
            if p.get("note") and col:
                badge = (f'<span class="badge" style="color:{col};border-color:{col}">'
                         f'{e(p["note"])}</span>')
            cit = ""
            if p.get("citations"):
                n = p["citations"]
                cit = f' <span class="cit">&middot; {n} citation{"s" if n != 1 else ""}</span>'
            venue = f'<i>{e(p.get("venue",""))}</i>' if p.get("venue") else ""
            year  = f' &middot; {p["year"]}' if p.get("year") else ""
            out.append(
                '<div class="pub"><div class="pnum">&bull;</div><div>'
                f'<div class="ptitle">{e(p.get("title",""))}{badge}</div>'
                f'<div class="pmeta">{e(p.get("authors",""))} &middot; {venue}{year}{cit}</div>'
                "</div></div>")
    return "".join(out)

def metrics_block(m):
    cells = [(m.get("publications"), "publications &amp; papers"),
             (m.get("citations"),    "citations"),
             (m.get("hIndex"),       "h-index"),
             (m.get("venues"),       "peer-reviewed venues")]
    inner = "".join(f'<div class="metric"><b>{v if v is not None else "&ndash;"}</b>'
                    f'<span>{l}</span></div>' for v, l in cells)
    return (f'<div class="metrics">{inner}</div>'
            f'<div class="refnote" style="margin:-4px 0 8px">Source: '
            f'{e(m.get("sourceLabel","Google Scholar"))}, retrieved '
            f'{datetime.date.today().isoformat()}.</div>')

def talks_block(talks):
    out = ['<div class="talks">']
    for t in talks:
        note = f' <span>({e(t["note"])})</span>' if t.get("note") else ""
        if t.get("scheduled"):
            note += ' <span class="sched">scheduled</span>'
        what = e(t["what"])
        if t.get("url"):
            what = f'<a href="{e(t["url"])}">{what}</a>'
        out.append(f'<div class="tw">{e(t["date"])}</div>'
                   f'<div class="tt">{what} <span>&middot; {e(t.get("where",""))}</span>{note}</div>')
    out.append("</div>")
    return "".join(out)

OUTREACH_GROUPS = [("podcast", "Podcasts"), ("column", "Columns"), ("blog", "Blog coverage"),
                   ("video", "Recorded talks"), ("report", "Reports &amp; notes"), ("press", "Press")]

def outreach_block(items):
    if not items:
        return ""
    known = {k for k, _ in OUTREACH_GROUPS}
    out = ['<div class="talks">']
    groups = OUTREACH_GROUPS + [(None, "Other")]
    for key, label in groups:
        g = [m for m in items if (m.get("kind") == key if key else m.get("kind") not in known)]
        if not g:
            continue
        out.append(f'<div class="ogrp">{label}</div>')
        for m in g:
            what = e(m.get("what", ""))
            if m.get("url"):
                what = f'<a href="{e(m["url"])}">{what}</a>'
            where = f' <span>&middot; {e(m["where"])}</span>' if m.get("where") else ""
            note = f' <span>({e(m["note"])})</span>' if m.get("note") else ""
            out.append(f'<div class="tw">{e(m.get("date",""))}</div>'
                       f'<div class="tt">{what}{where}{note}</div>')
    out.append("</div>")
    return "".join(out)

# ---------------------------------------------------------------- build
def build(cv, pubdata, short=False):
    p = cv["person"]
    body, dot = [], {"i": 0}

    def sec(title, inner):
        c = DOTS[dot["i"] % len(DOTS)]; dot["i"] += 1
        return f'<section><h2 style="--dot:{c}">{title}</h2>{inner}</section>'

    summary = (cv.get("summaryShort") or cv["summary"]) if short else cv["summary"]
    body.append(sec("Summary", f'<p class="lead">{e(summary)}</p>'))
    body.append(sec("Academic positions", rows(cv["positions"], "years", org_row)))

    edu = rows(cv["education"], "years", org_row)
    if not short:
        edu += '<div class="pgroup">Visiting</div>' + rows(cv["visiting"], "years", org_row)
    body.append(sec("Education", edu))

    if not short:
        body.append(sec("Further positions", rows(cv["otherPositions"], "years", org_row)))

    only = ("published", "review") if short else None
    body.append(sec("Research", metrics_block(pubdata.get("metrics", {}))
                    + publications_block(pubdata.get("publications", []), only=only)))

    body.append(sec("Teaching", rows(cv["teaching"], "years", teach_row)))

    if not short:
        body.append(sec("Selected talks", talks_block(cv["talks"])))
        if cv.get("outreach"):
            body.append(sec("Outreach, media coverage &amp; other output",
                            outreach_block(cv["outreach"])))
        body.append(sec("Organized conferences &amp; seminars",
                        rows(cv["organized"], "date",
                             lambda it: f'{e(it["what"])}<br><span>{e(it.get("role",""))}</span>')))
        body.append(sec("Policy work",
                        rows(cv["policy"], "year",
                             lambda it: f'{e(it["what"])} <span>&middot; {e(it.get("role",""))}</span>')))

    body.append(sec("Grants &amp; awards", rows(cv["grants"], "year", lambda it: e(it["what"]))))

    if not short:
        body.append(sec("Academic service",
                        '<div class="kv">'
                        f'<div class="k">Peer review</div><div class="v">{e(cv["service"]["reviewing"])}</div>'
                        f'<div class="k">Memberships</div><div class="v">{e(cv["service"]["memberships"])}</div>'
                        "</div>"))
        body.append(sec("Doctoral courses",
                        '<ul class="plain">'
                        + "".join(f"<li>{e(c)}</li>" for c in cv["doctoralCourses"]) + "</ul>"))

    body.append(sec("Research interests &amp; skills",
                    '<div class="kv">'
                    f'<div class="k">Interests</div><div class="v">{e(cv["interests"])}</div>'
                    f'<div class="k">Languages</div><div class="v">{e(cv["skills"]["languages"])}</div>'
                    f'<div class="k">Software</div><div class="v">{e(cv["skills"]["software"])}</div>'
                    "</div>"))

    if not short:
        refs = "".join(f'<div><b>{e(r["name"])}</b><br><span>{e(r["org"])}</span></div>'
                       for r in cv["references"]["people"])
        body.append(sec("References", f'<div class="refgrid">{refs}</div>'
                        f'<div class="refnote">{e(cv["references"]["note"])}</div>'))

    links = [f'<a href="mailto:{e(p["email"])}">{e(p["email"])}</a>']
    links += [f'<a href="{e(l["url"])}">{e(l["label"])}</a>' for l in p["links"]]
    if short:
        links.append('<a href="https://sahlimatthias.com/cv.pdf">full CV</a>')

    b64 = lambda f: "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()
    html_out = (TPL.read_text(encoding="utf-8")
                .replace("__NAME__", e(p["name"]))
                .replace("__ROLE__", e(p["role"]))
                .replace("__AFF__", e(p["affiliation"]))
                .replace("__ADDRESS__", e(p["address"]))
                .replace("__LINKS__", ' <span>&middot;</span> '.join(links))
                .replace("__PHOTO__", b64(PHOTO))
                .replace("__BODY__", "".join(body)))

    out = OUT_SHORT if short else OUT_FULL
    tmp = ROOT / "pdf" / "_cv_render.html"
    tmp.write_text(html_out, encoding="utf-8")

    from playwright.sync_api import sync_playwright
    stamp = datetime.date.today().strftime("%d %B %Y")
    kind = "Curriculum Vitae &mdash; short" if short else "Curriculum Vitae"
    foot = ('<div style="width:100%;font-family:Inter,sans-serif;font-size:7pt;color:#83888F;'
            'padding:0 15mm;display:flex;justify-content:space-between;">'
            f'<span>Matthias Sahli &middot; {kind} &middot; last updated {stamp}</span>'
            '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page()
        pg.goto(tmp.as_uri(), wait_until="networkidle")
        pg.pdf(path=str(out), format="A4", print_background=True,
               display_header_footer=True, header_template="<div></div>", footer_template=foot,
               margin={"top": "15mm", "bottom": "17mm", "left": "15mm", "right": "15mm"})
        br.close()
    tmp.unlink(missing_ok=True)
    print(f"OK - {out.name} ({out.stat().st_size // 1024} KB)")

def load_publications():
    if "--local" in sys.argv:
        print(f"publications: local {PUBS} (--local)")
        return json.loads(PUBS.read_text(encoding="utf-8"))
    try:
        req = urllib.request.Request(PUBS_URL, headers={"User-Agent": "cv-builder"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        print(f"publications: live from {PUBS_URL} (generated {data.get('generated','?')})")
        return data
    except Exception as ex:
        if PUBS.exists():
            print(f"publications: live fetch failed ({ex}) - using local {PUBS}")
            return json.loads(PUBS.read_text(encoding="utf-8"))
        sys.exit(f"cannot load publication data: {ex}")

def main():
    for f in (CV, TPL, PHOTO):
        if not f.exists():
            sys.exit(f"missing: {f}")
    pubdata = load_publications()
    cv = json.loads(CV.read_text(encoding="utf-8"))
    build(cv, pubdata, short=False)
    build(cv, pubdata, short=True)

if __name__ == "__main__":
    main()
