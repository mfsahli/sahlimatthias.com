# sahlimatthias.com — neue Website

Moderne, interaktive One-Page-Website mit wöchentlich automatisch aktualisierten
Research-Daten (OpenAlex + Semantic Scholar, kein Google-Scholar-Scraping).

## Struktur

```
03_website/
├── index.html                  ← die komplette Website (CSS/JS/Fotos inline)
├── cv.pdf                      ← dein CV (im Footer verlinkt)
├── CNAME                       ← Domain-Datei für GitHub Pages
├── data/publications.json      ← kuratierte Publikationsdaten (deine "Quelle der Wahrheit")
├── scripts/update_publications.py  ← holt Zitationen/Papers von den APIs
└── github/workflows/update-publications.yml   ← wöchentlicher Cron (Mo 06:00 UTC)
```

> ⚠️ **Wichtig:** Der Ordner heisst hier `github` (ohne Punkt), weil versteckte
> Workflow-Dateien nicht direkt in deinen OneDrive-Ordner geschrieben werden
> konnten. Vor dem Push auf GitHub den Ordner in `.github` (mit Punkt) umbenennen:
> `mv github .github`


## Live schalten (einmalig, ca. 20 Minuten)

1. **Repo erstellen:** Auf github.com ein neues öffentliches Repository anlegen
   (z.B. `sahlimatthias.com`) und den kompletten Inhalt dieses Ordners pushen.
   Wichtig: der Ordner `.github/workflows/` muss mitkommen.
2. **Pages aktivieren:** Repo → Settings → Pages → Source: "Deploy from a branch",
   Branch `main`, Ordner `/ (root)`. Nach ~1 Minute läuft die Seite unter
   `https://<username>.github.io/<repo>/`.
3. **Domain anbinden:** Settings → Pages → Custom domain: `sahlimatthias.com`
   eintragen ("Enforce HTTPS" aktivieren, sobald verfügbar). Beim Domain-Anbieter
   (dort, wo sahlimatthias.com registriert ist):
   - Die bestehende Weiterleitung zu Google Sites entfernen.
   - 4 A-Records für `@` setzen: `185.199.108.153`, `185.199.109.153`,
     `185.199.110.153`, `185.199.111.153`
   - Optional CNAME-Record `www` → `<username>.github.io`
4. **Auto-Update testen:** Repo → Actions → "Update publication data" →
   "Run workflow". Danach läuft es jeden Montag von selbst.

## Google-Scholar-Zahlen aktivieren (empfohlen)

Google blockiert direktes Scholar-Scraping — deshalb kommen die echten
Scholar-Zahlen über die offizielle **SerpAPI Google Scholar Author API**:

1. Gratis-Account auf [serpapi.com](https://serpapi.com) erstellen
   (Free-Plan: 100 Abfragen/Monat — der Wochenlauf braucht ~4-5).
2. API-Key kopieren → im GitHub-Repo unter Settings → Secrets and variables →
   Actions → "New repository secret" als **`SERPAPI_KEY`** hinterlegen.
3. Fertig. Ab dem nächsten Lauf zeigen Website-Metriken, Chart und die
   "X cit."-Badges deine Scholar-Zahlen (inkl. zusammengeführter Versionen),
   der Jahres-Graph kommt von Scholar, und jedes Paper verlinkt direkt auf
   seinen Scholar-Eintrag. Die Quellen-Labels auf der Seite stellen sich
   automatisch auf "Google Scholar" um.

Ohne Key läuft alles weiter wie bisher (Semantic Scholar/OpenAlex, etwas
konservativere Zählung).

## Wie das Auto-Update funktioniert

- `update_publications.py` holt deine Papers + Zitationszahlen von
  **Semantic Scholar** und die Zitationen-pro-Jahr von **OpenAlex** (beides
  offizielle, freie APIs — Google Scholar wird verlinkt, aber nicht gescrapt,
  da Google das blockiert und verbietet).
- Deine kuratierten Felder in `data/publications.json` (`finding`, `tags`,
  `links`, `status`, `note`) werden **nie überschrieben** — nur Zitationszahlen
  und DOIs werden ergänzt.
- **Neue Papers** (z.B. wenn ein Working Paper erscheint) werden automatisch
  entdeckt und angehängt. Sie erscheinen zunächst ohne Themen-Tags — einfach in
  `data/publications.json` `tags` (`ip`, `art`, `dig`, `sus`), `finding` und
  `status` (`published` / `working` / `other`) ergänzen.
- Beim ersten erfolgreichen Lauf loggt das Skript deine OpenAlex-Author-ID —
  diese in `scripts/update_publications.py` bei `OPENALEX_AUTHOR_ID` eintragen,
  dann ist die Zuordnung dauerhaft eindeutig. Sobald OpenAlex-Daten da sind,
  erscheint automatisch das zweite Chart "Citations per year".
- Hinweis: OpenAlex/Semantic Scholar zählen konservativer als Google Scholar —
  die Zahlen sind daher etwas tiefer als auf deinem Scholar-Profil. Die Quelle
  ist auf der Seite transparent angegeben.

## Arbeitsteilung Mensch/Routine (mit SERPAPI_KEY)

Dein Google-Scholar-Profil ist die "Quelle der Wahrheit" für alles Publizierte —
du pflegst es ja ohnehin (Versionen zusammenführen, falsche Einträge löschen).
Die Wochenroutine übernimmt von dort automatisch:

- **Alle publizierten Papers**: neue Einträge auf deinem Scholar-Profil werden
  automatisch als "published" auf die Website übernommen (Titel, Autoren, Venue,
  Jahr, Zitationen, Direktlink) — du musst nur noch optional Tags und den
  Kernbefund ("finding") in `data/publications.json` ergänzen.
- **Zitationszahlen**: exakt deine Scholar-Zahlen, inkl. aller zusammengeführten
  Versionen. Gesamt, h-Index, pro Paper und pro Jahr.
- **Working-Paper-Erkennung**: erscheint ein Working Paper von der Website
  plötzlich mit Journal auf Scholar, schreibt der Lauf einen HINT ins
  Action-Log — dann Status/Venue in `data/publications.json` umstellen.

**Du pflegst manuell nur noch:** Working Papers und Submission-Pipeline
(status "working", note "under review at …") sowie Kernbefunde/Tags/Extra-Links.
Von der Routine gesetzte Felder überschreiben deine manuellen Texte nie.

## Inhalte pflegen

- **Publikationen:** nur `data/publications.json` editieren, dann einmal
  `python3 scripts/update_publications.py` laufen lassen (oder den Action-Workflow
  manuell triggern) — das Skript schreibt die Daten in `index.html`.
- **Texte/Timeline/Teaching:** direkt in `index.html` (Abschnitte sind
  kommentiert bzw. leicht auffindbar: `TL = [...]` für die Timeline).
- **Noch zu tun:** Im Footer die Platzhalter-Links für **ORCID, LinkedIn,
  ResearchGate** durch deine echten Profil-URLs ersetzen (in `index.html` nach
  `footlinks` suchen).

## Interaktive Elemente pflegen

- **Terminal auf der Landing:** versteht Stichworte (kein Server, kein API-Key —
  die Seite bleibt statisch). Intents/Antworten stehen in `index.html` im Array
  `ROUTES` und sind frei erweiterbar. Ein "echtes" LLM-Chat-Feld wäre möglich,
  bräuchte aber ein kleines Backend (z.B. Cloudflare Worker mit API-Key, kostet) —
  bei Bedarf später nachrüstbar.
- **Thesis-Themen für Studierende:** im Array `THESIS` in `index.html` — Titel,
  Pitch, "You would…", Methoden. Jede Karte hat einen vorbefüllten
  Mail-Link ("I want this one").
- **Timeline:** Array `TL` in `index.html` (Jahr, Titel, Detailtext, Link).

## Design-Notizen

- Farbpunkte in der Navigation = Erbe deiner alten Google-Sites-Seite (🔴🟠🟢):
  Rot = nach oben, Orange = zu Research, **Grün = Dark Mode** (Easter Egg).
- Akzentpalette ist farbfehlsichtigkeits-geprüft (validiert für Light- und
  Dark-Surface). Schriften: Fraunces + Inter (Google Fonts).
- Fotos: Florian Spring (Credit im Footer und auf dem Hero-Bild).
