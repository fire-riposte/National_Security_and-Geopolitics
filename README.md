# NatSec Brief

A weekday news brief on US national security, espionage and great-power
competition. A Claude Code routine runs every weekday morning, reads about 30
news feeds, picks the stories that matter, and commits a short sourced summary
to this repo. The `docs/` folder is a Jekyll site, ready for GitHub Pages.

## How it works

1. **6:45am ET, Monday to Friday**: the routine starts a Claude Code cloud
   session with this repo cloned.
2. **`scripts/fetch_feeds.py`** pulls every feed in `feeds.toml`, keeps stories
   published since the last brief, drops links already cited in the past ten
   days, scores each story against the keyword groups, merges duplicates, and
   writes a ranked list to `build/candidates.md`.
3. **Claude** follows `BRIEFING.md`: it picks 8 to 12 stories, checks thin ones,
   and writes `docs/_posts/YYYY-MM-DD-brief.md` with a link for every claim.
4. The brief is committed and pushed to `main`. With Pages on, the site
   rebuilds on its own.

## Files

| Path | What it's for |
| --- | --- |
| `feeds.toml` | News sources and the keyword scoring. Add or remove feeds here. |
| `BRIEFING.md` | Editorial rules and the brief template. Change focus or tone here. |
| `scripts/fetch_feeds.py` | Feed fetcher and ranker. Standard-library Python, no installs. |
| `tests/` | Unit tests for the fetcher: `python3 -m unittest discover -s tests` |
| `docs/` | The Jekyll site (minima theme). Briefs live in `docs/_posts/`. |

## Setup checklist

- [ ] **Allow the feed domains** in the cloud environment. In a Claude Code
  session, open the environment menu in the title bar, choose Edit, set Network
  access to **Custom**, paste the list below (one per line), and keep **Also
  include default list of common package managers** checked.
- [ ] **Create the routine** (weekdays, 6:45am ET) with the prompt below.
- [ ] **Turn on GitHub Pages** when ready: Settings > Pages > Deploy from a
  branch > `main` / `/docs`. A private repo needs GitHub Pro for this, and the
  published site is public either way.

```text
www.spytalk.co
www.thecipherbrief.com
therecord.media
cyberscoop.com
www.lawfaremedia.org
www.justsecurity.org
www.reddit.com
www.justice.gov
www.fbi.gov
www.dni.gov
www.war.gov
www.defense.gov
www.defenseone.com
breakingdefense.com
defensescoop.com
news.usni.org
www.twz.com
www.defensenews.com
warontherocks.com
thediplomat.com
jamestown.org
foreignpolicy.com
www.understandingwar.org
www.csis.org
www.atlanticcouncil.org
news.google.com
feeds.bbci.co.uk
www.bbc.com
```

### Routine prompt

```text
Produce today's NatSec Brief for this repository.

1. Follow BRIEFING.md in the repo root exactly.
2. Commit only the new brief in docs/_posts/ with the message "Brief: YYYY-MM-DD"
   and push it to main (git push origin HEAD:main).
3. If the push to main is rejected, push to a branch named
   claude/brief-YYYY-MM-DD instead and say so in your final message.
4. Do not change any other file. End with one line: how many stories made the
   brief and which feeds failed.
```

## Costs and limits

- Each run is a Claude Code cloud session, so it draws on the one-time cloud
  sessions credit while that lasts, then on your normal plan usage. Check
  claude.ai/settings/usage after the first few runs to see the real cost per
  brief.
- Routines have a daily cap on scheduled runs. One brief a day is well under it.
- To cut cost: lower `max_candidates` in `feeds.toml`, lower the article lookup
  limit in `BRIEFING.md`, or run the routine on a smaller model.

## Running it by hand

```bash
python3 scripts/fetch_feeds.py          # writes build/candidates.md
python3 -m unittest discover -s tests   # runs the tests
```

Local runs need network access to the feed domains.
