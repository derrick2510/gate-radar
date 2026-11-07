# Publish GATE RADAR v3 with hourly news updates

**What this is:** A static website that shows hand-researched, source-linked examples plus an automated headline feed. GitHub Actions fetches RSS on an hourly schedule and publishes an updated GitHub Pages site. **This download does not run an hourly service until you configure it on GitHub.** No paid domain or API key required for the default setup.

## Recommended: GitHub Pages, one provider, no domain purchase

1. Extract `GATE_RADAR_v3_hourly.zip` on your computer. The ZIP contains `index.html`, `data/`, `scripts/`, `tests/`, and `.github/workflows/news.yml`.
2. Sign in at https://github.com/new. Create a new repository, for example `gate-radar`. Choose **Public** for GitHub Pages on GitHub Free. Do **not** upload any private client or internal company information. Check with GATE IT before publishing any company-branded site. (Private/restricted access will require an approved hosting and authentication design.)
3. Upload **the contents of the extracted folder**, preserving the directory structure, to the `main` branch. You may drag the extracted directory contents onto GitHub's **Add file → Upload files** area. Confirm the workflow is at `.github/workflows/news.yml` and not inside a nested `gate_radar_v3` folder.
4. In the repository, open **Settings → Pages → Build and deployment → Source → GitHub Actions**. Save the setting.
5. Open **Actions → Refresh GATE RADAR industry news → Run workflow → Run workflow**. Approve Actions for the repository if prompted. The first run can take a few minutes.
6. The website will be available at `https://YOUR-USERNAME.github.io/gate-radar/` (substitute your GitHub username and repository name). The deployed site and the **Actions** tab show whether the first run succeeded.
7. The collector checks for new headlines around **17 minutes past each hour (UTC)**. GitHub explicitly says scheduled runs may be delayed or missed. Users visiting a page that's already open will check for the refreshed JSON every 15 minutes.

**If deployment fails:** Check the Actions run log. If the job cannot push its JSON update, open Settings → Actions → General → Workflow permissions and confirm the repository allows workflows to write contents (organization controls may override). If GitHub Pages reports an authorization error, recheck Settings → Pages → Source → GitHub Actions and the environment's permitted deploy branches.

## Keep using Netlify instead

You may connect the same **GitHub repository** to your existing Netlify site using its **Git/continuous deployment** connection. The scheduled workflow also saves new `data/feed.json` to the repo; Netlify is expected to rebuild on those changes. A **manual Netlify Drop upload alone will not keep updating**, because it cannot run GitHub Actions or pick up subsequent JSON changes. Check that GitHub-to-Netlify automatic builds are enabled after connecting.

## What the system does, and doesn't do

- Searches 10 Google News RSS query feeds (UK edition) across agency wins, sport, campaigns, entertainment, production, social content and tenders, every hour **when GitHub Actions is enabled**.
- Maintains up to 200 unique recent headlines (14 days), using text-only headlines and a link to the publisher via Google News. It does **not** scrape paywalled pages or reproduce article bodies.
- Offers *heuristic* production opportunity scores and suggested opening questions. **These are not confirmations of projects, budgets, supplier selection, relationships, or factual article claims.** Always read the original and check the commissioning chain before outreach.
- Shows 9 manually researched examples and their published contact routes. The collector **never invents personal emails or LinkedIn identities**. For new stories, it offers a LinkedIn people search only when a company name is detected; users must verify the person and role.
- Stores ownership, follow-up, stages and notes **locally in each user's browser**. There is no team-wide sync yet. Export CSV if you want to share; keep sensitive notes out of public repositories.
- Shows source health (number of successful feeds, failed queries, last successful fetch and stale flags). If feeds are unavailable, old data is retained where possible rather than showing fictitious fresh updates.
- Does not send emails, contact people, or connect to HubSpot automatically.

## Source reliability & rights

Google News RSS query feeds are a **community-documented, undocumented service**, not a guaranteed API. Feeds can change, have incomplete coverage, contain duplicates or link through Google News rather than straight to a publisher. The feed collector is an intelligence *lead finder*, not fact-checking or a source-of-truth database. The interface retains source and review status. Publisher content and trademarks remain with their owners; use headlines/links, not republished article text.

## Customize

- Edit query categories in `scripts/collect_news.py` under `SEARCHES`.
- Edit priority terms and title-matching lists under `BRANDS`, `AGENCIES`, `intelligence()`.
- The seeded verified research examples live in `data/curated.json`. The HTML contains an embedded copy for offline preview. After changing curated JSON, run `python make_index.py` and commit `index.html` so both agree.
- Run tests locally with `python -m unittest discover -s tests -v`.
- To simulate offline collection, run `python scripts/collect_news.py --fixture tests/sample_feed.xml` after supplying a valid RSS file. To collect live news on your own computer (if internet access is enabled), run `python scripts/collect_news.py`.

## Limits / future upgrade

For **shared** notes, account ownership and a proper collaboration workflow, add an authenticated database (e.g. Supabase) and consider CRM synchronization after IT approval. A company-private dashboard is a different architecture from this public demo. For reliability beyond a hobby/prototype use case, replace Google News RSS queries with licensed feeds or a commercial data source with service guarantees.