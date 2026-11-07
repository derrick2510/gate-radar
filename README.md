# GATE RADAR v4 — Target-first production business development intelligence

**Live public preview:** https://derrick2510.github.io/gate-radar/

- Hourly Google News RSS checks focusing on **UK, EMEA and US** creative and media production, account wins, campaigns, talent agencies and production tenders.
- Optional **private agency hitlist** held only in a GitHub Actions secret: `GATE_TARGET_AGENCIES`. The list is **not committed** to this public repo. Each hourly run monitors 8 groups of 8 names; a complete sweep of a long list generally takes several hours.
- When a named agency matches a headline, the site flags it as a **name match to verify**, not proof of a confirmed relationship or live brief.
- Talent agencies/management/creator representation have their own monitoring category.
- Separate headline-evidenced region vs search-market context; do not treat market filters as verified campaign geography.
- Priority scores and conversation prompts are heuristics. The system does not invent contacts, verified budgets, project availability or supplier assignments.
- Outreach notes, saved stories and ownership are saved **locally** in each visitor's browser; not shared or private by default.

## Enable private target watch

In **Settings → Secrets and variables → Actions → New repository secret**, create `GATE_TARGET_AGENCIES` with one agency name per line. Save and manually rerun **Actions → Refresh GATE RADAR industry news → Run workflow**. The dashboard will show the number of configured agency names, but never publishes the entire hitlist. **Google News receives agency names in search requests** and the public website displays individual matched headlines; seek company approval.

Read [docs/SETUP.md](docs/SETUP.md) for setup, limitations, editing and troubleshooting. No commercial API subscription is needed for the starter, though RSS availability, coverage and scheduling are not guaranteed.

Technical stack: static HTML/CSS/JS, Python standard library, GitHub Actions, GitHub Pages. Run tests with `python -m unittest discover -s tests -v`.