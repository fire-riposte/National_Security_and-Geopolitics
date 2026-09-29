# NatSec Brief

A weekday news brief on US national security, espionage and great-power
competition, plus German and Israeli intelligence and military news. A Claude
Code routine runs every weekday morning, reads about 40 news feeds (some in
German), picks the stories that matter, and commits a short sourced summary
in English to this repo. The `docs/` folder is a Jekyll site, ready for GitHub Pages.

The site also carries the **Taiwan Dashboard Clock** at `/taiwan-clock/`: a
minutes-to-midnight board on a PLA use of force against Taiwan, rescored weekly
(see [below](#taiwan-dashboard-clock)).

## How it works

1. **6:45am ET, Monday to Friday**: the routine starts a Claude Code cloud
   session with this repo cloned.
2. **`scripts/fetch_feeds.py`** pulls every feed in `feeds.toml`, keeps stories
   published since the last brief, drops links already cited in the past ten
   days, scores each story against the keyword groups, merges duplicates, and
   writes a ranked list to `build/candidates.md`.
3. **Claude** follows `BRIEFING.md`: it picks 8 to 12 stories (plus up to 4 on
   Germany and Israel), checks thin ones, and writes
   `docs/_posts/YYYY-MM-DD-brief.md` with a link for every claim.
4. The brief is committed and pushed to `main`. With Pages on, the site
   rebuilds on its own.

## Files

| Path | What it's for |
| --- | --- |
| `feeds.toml` | News sources and the keyword scoring. Add or remove feeds here. |
| `BRIEFING.md` | Editorial rules and the brief template. Change focus or tone here. |
| `scripts/fetch_feeds.py` | Feed fetcher and ranker. Standard-library Python, no installs. |
| `tests/` | Unit tests for the fetcher and the clock: `python3 -m unittest discover -s tests` |
| `docs/` | The Jekyll site. Briefs live in `docs/_posts/`, styling in `docs/assets/css/machine.css`. |
| `docs/_data/taiwan_clock.json` | The Taiwan clock's scores, sources and log. The page and homepage tile render from it. |
| `scripts/taiwan_clock.py` | Validates the clock data and logs each weekly reading. Standard-library Python. |
| `.claude/skills/machine-design/` | The Machine design system spec, so future Claude sessions keep the look consistent. |

## Design

The site uses the [Machine](https://www.typeui.sh/design-skills/machine) design
system from TypeUI: a dark blueprint monitor with navy screens, electric-blue
grid borders, cyan mono readouts and coral stamps. Fonts (Space Grotesk,
Manrope, Share Tech Mono) are self-hosted under the SIL Open Font License, so
the site makes no third-party requests.

## Setup checklist

- [x] **Allow the feed domains** in the cloud environment the routine uses. In a Claude Code
  session, open the environment menu in the title bar, choose Edit, set Network
  access to **Custom**, paste the list below (one per line), and keep **Also
  include default list of common package managers** checked.
- [x] **Allow the Germany and Israel feed domains**: add the last 7 lines of the
  list below (from `www.presseportal.de` down) to the same environment. Until
  then those feeds fail with a 403 and show up under failed feeds.
- [x] **Create the routine** (weekdays, 6:45am ET) with the prompt below.
- [x] **Finish the routine's settings** at claude.ai/code/routines: open
  "NatSec Brief (weekdays)", choose Edit, add this repository, and pick Sonnet
  as the model.
- [x] **Make `main` the default branch**: Settings > General > Default branch.
- [ ] **Create the Taiwan clock routine** (Mondays, 7:20am ET) with the
  prompt under [Weekly routine](#weekly-routine), on this repository.
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
www.odni.gov
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
understandingwar.org
www.csis.org
www.atlanticcouncil.org
news.google.com
feeds.bbci.co.uk
www.bbc.com
www.presseportal.de
www.verfassungsschutz.de
augengeradeaus.net
www.timesofisrael.com
www.haaretz.com
israel-alma.org
www.inss.org.il
```

### Routine prompt

```text
Produce today's NatSec Brief for the GitHub repository
fire-riposte/National_Security_and-Geopolitics.

0. Work in a checkout of that repository's main branch. If this session doesn't
   already have one, clone https://github.com/fire-riposte/National_Security_and-Geopolitics
   and check out main.
1. Follow BRIEFING.md in the repo root exactly.
2. Commit only the new brief in docs/_posts/ with the message "Brief: YYYY-MM-DD"
   and push it to main (git push origin HEAD:main).
3. If the push to main is rejected, push to a branch named
   claude/brief-YYYY-MM-DD instead and say so in your final message.
4. Do not change any other file. End with one line: how many stories made the
   brief and which feeds failed.
```

## Taiwan Dashboard Clock

The page at `/taiwan-clock/` scores Gregory J. Moore's 13 dials from
["Xi Jinping's Taiwan Dashboard"](https://www.airuniversity.af.edu/JIPA/Display/Article/4168508/xi-jinpings-taiwan-dashboard-considering-xis-calculus-for-a-possible-move-on-ta/)
(Journal of Indo-Pacific Affairs, Spring 2025), adds seven indications and
warning indicators, and turns them into minutes to midnight. Midnight means the
PLA begins a major use of force against Taiwan: an invasion, or a blockade
enforced by fire.

- `docs/_data/taiwan_clock.json` is the only source of truth. The page and the
  homepage tile are built from it by Jekyll, with no JavaScript except the
  ticking second hand.
- `scripts/taiwan_clock.py` holds the scoring formula. `check` validates the
  file (including no em dashes anywhere) and `log --date --note` stores the new
  reading and adds a line to the log. The page restates the formula under "How
  the clock is set", so change both together.
- A weekly routine rescores it. Its prompt is below.

### Weekly routine

Run it **Mondays at 7:20am ET**, after the 6:45am brief, so the two don't race
on pushes to `main`. It needs web search and fetch across many news sites. If
its environment uses the custom allowlist above, check the first run for
blocked hosts, or give it an environment with wider network access.

```text
Weekly re-score of the Taiwan Dashboard Clock in this repo. The source of truth
is `docs/_data/taiwan_clock.json`. The page at `/taiwan-clock/` and the homepage
tile render from it at build time. The framework is Gregory J. Moore's
"Xi Jinping's Taiwan Dashboard" (JIPA, Spring 2025) plus an indications-and-warning
(I&W) layer. Midnight means the PLA begins a major use of force against Taiwan:
an invasion, or a blockade enforced by fire.

1. `git pull`, then run `python3 scripts/taiwan_clock.py check` and read the
   JSON to see last week's scores and log.
2. Research what changed in the past 7 days (web search and fetch). Cover every
   dial and indicator:
   - PLA leadership, readiness and purges
   - China GDP and economic data
   - NCCU identity survey (updates in Jan and Jul)
   - China demographics
   - TSMC overseas fab progress
   - US chip export controls and China's response
   - US arms sales to Taiwan (the frozen ~$14B package) and US commitment signals
   - US-Taiwan training and interoperability
   - US munitions stocks and replenishment
   - US hypersonic fielding and defense
   - US-China relations and summits
   - Xi's rhetoric on US intentions
   - Taiwan politics (Nov 28, 2026 local elections, the KMT under Cheng Li-wun,
     the 2028 race)
   - PLA air and naval activity (Taiwan MND, Taiwan Security Monitor, AEI China
     & Taiwan Update)
   - Large-scale PLA drills
   - Amphibious lift, ro-ro ferries and landing barges
   - China strategic stockpiling
   - Coast guard, gray-zone and quarantine moves
   - Domestic mobilization signals
   - Legal and rhetorical groundwork
3. Scoring rules:
   - Dial `reading` is an integer from -2 (strong reason for Beijing to wait)
     to +2 (strong reason to act soon), judged by Moore's logic for that dial
     applied to current conditions. `trend` is `rising` (pressure to act
     rising), `easing`, or `steady`.
   - I&W `level` is 0 none, 1 watch, 2 elevated, 3 warning. A 3 means concrete
     preparation for imminent operations: ferries requisitioned and massing,
     blood or medical stockpiling, PLA leave cancelled, evacuation advisories.
   - Factor `status` is `active`, `strengthened`, or `weakened`.
   - Change a score only on sourced evidence. Think like a senior warning
     analyst and don't overreact to a single news item.
   - Keep each assessment to 2 to 4 plain sentences with no em dashes, and
     keep 1 to 3 sources per card as `{title, url}`. Use real https URLs you
     actually read.
   - Set `updated` to today on every dial or I&W card you touch.
4. Edit the JSON:
   - Set `as_of` (YYYY-MM-DD) and `as_of_label` (e.g. "Oct 5, 2026").
   - Rewrite `summary` in 3 to 5 sentences, ending with the midnight definition.
   - Remove past entries from `dates` and add new ones.
5. Run `python3 scripts/taiwan_clock.py log --date <today> --note "<one sentence on what moved, or No change.>"`,
   then run the tests. Both must pass. If `check` reports problems, fix the
   data rather than the script.
6. Commit to `main` with a message like `taiwan-clock: weekly re-score YYYY-MM-DD (NN min)`
   and push.
7. End with a short summary for Jason covering:
   - the new minutes and the change from last week
   - which dials or indicators moved, and why
   - what to watch next
   If any I&W indicator reached level 2 for the first time, or level 3 at all,
   say that first.

Style: professional but conversational, no em dashes, no buzzwords.
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
python3 scripts/taiwan_clock.py check   # validates the Taiwan clock data
python3 -m unittest discover -s tests   # runs the tests
```

Local runs need network access to the feed domains.
