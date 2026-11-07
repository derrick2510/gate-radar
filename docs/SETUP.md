# GATE RADAR v4 — Configure the targeted industry radar

## Current production deployment

Repository: https://github.com/derrick2510/gate-radar  
Expected public website: https://derrick2510.github.io/gate-radar/

The scheduled workflow refreshes the public feed about 17 minutes past each hour (UTC), subject to GitHub Actions delays. A newly opened browser loads `data/feed.json`; already open tabs recheck it approximately every 15 minutes.

## Enable your private agency hitlist (required for target-specific monitoring)

1. Go to **GitHub repository → Settings → Secrets and variables → Actions → New repository secret**.  
2. Enter the exact name **`GATE_TARGET_AGENCIES`**.  
3. Paste your agency names **one per line** as the secret value (no bullets, no HTML table markup). Do not add the list to repository files, issues or commit messages.  
4. Click **Add secret**, then **Actions → Refresh GATE RADAR industry news → Run workflow**.  
5. Check `data/feed.json`'s `monitoring_mode` becomes `target-first` and `target_agency_count_configured` is greater than zero; the full list never appears in that JSON.

The collector rotates **8 search batches of up to 8 names each hourly** to keep RSS querying practical. For an approximately 181-name list, a full scan normally takes around three hourly runs. Publishing a new hitlist requires updating the secret and running the workflow again. Search engines receive the agency search terms; the public dashboard displays matched headlines and names when relevant. Keep this limitation in mind when choosing whether to proceed with a corporate-sensitive target list.

## What counts as news worth checking

- UK, EMEA and US agency/brand account wins and appointments
- New branded film, commercial, sport or social campaigns
- Film/video production tenders or RFPs (verify the buyer's official notice)
- Talent agencies, creator/artist management, athlete representation and roster announcements
- Specifically named agency news from the hitlist: matches prioritized ahead of more generic reporting

**Market tags** are based on recognizable geographic words *in the headline* when unambiguous; otherwise marked **To verify**. A Google News search country/locale is a discovery parameter, not verified location or commercial territory.

**No personal emails are invented.** Named contacts and public links in the curated research directory are separate from automatically collected headlines; their current roles still require checking. No open production budget is assumed from a campaign launch.

## Monitoring health and limitations

GitHub Actions can occasionally delay or skip scheduled jobs. Google News RSS is an undocumented feed with no availability guarantee. Results are headline-level, not article-body fact-checking. Articles may duplicate, appear late, or concern similarly named entities; read sources before outreach.

The public GitHub Pages site and public feed can be read by anyone with the link. Outreach stages and notes are saved in each person's browser only, not shared. Obtain GATE approval and use an authenticated system before storing sensitive client details or internal activity centrally.

## Run locally

`python -m unittest discover -s tests -v`  
`python scripts/collect_news.py` (network needed)  
`python make_index.py` to regenerate `index.html` from `data/curated.json`  

For a simple offline test: `python scripts/collect_news.py --fixture tests/sample_feed.xml` (backs up existing `data/feed.json` first).