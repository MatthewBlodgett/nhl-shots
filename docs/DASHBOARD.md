# GitHub Pages paper dashboard

The static dashboard has Opportunities, Performance and Health views. It reads
`data/review.json` on odds-records directly from GitHub. The existing recorder
exports that summary after updating reports/health and includes it in its normal
archive commit. Opening, refreshing or browsing players makes no odds requests
and consumes no Odds API credits. No key is accepted or embedded in the page.

The summary contains bounded latest opportunity/player observations, aggregate
performance, quota/health and research summaries. It excludes the internal request
ledger and reproducible raw model histories. Public research remains unproven.
A failed collection or Git push leaves older data; the browser marks it stale
from its recorded run timestamp. Expiry is recalculated on refresh and every
30 seconds while the page is open. Started games and invalid/future timestamps
cannot remain fresh. Raw GitHub/CDN caching can briefly delay archive visibility;
the page is not continuous market monitoring or live price verification.

## Publishing

`.github/workflows/dashboard-pages.yml` tests/builds the site and uploads a Pages
artifact on the dashboard branch/PR. Deployment runs only from master, using
GitHub's pinned official Pages actions and the github-pages environment.
The static build is `python build_dashboard.py --output dist`.
The Python HTTP API remains local; this deployment publishes only HTML/JavaScript.

A repository administrator must enable Pages once:

1. Open https://github.com/MatthewBlodgett/nhl-shots/settings/pages
2. Under Build and deployment, set Source to **GitHub Actions**.
3. Run **Publish research dashboard** from Actions, or rerun its failed deployment.

The connected repository tools do not expose Pages administration. GitHub's
configure-pages action also requires an administration-capable token to enable
Pages automatically; the normal Actions token is insufficient for that setup.
No additional token or paid service is needed when the owner enables the setting.

Expected address after successful deployment:
https://matthewblodgett.github.io/nhl-shots/

That address must not be described as active until deployment and an HTTP check
succeed. No notifications or autonomous agent are deployed by this workflow.

## Local verification

`python build_dashboard.py --data-dir ../records/data --output /tmp/nhl-pages`
creates a current public summary and the static page. Serve that output with a
local HTTP server; it reads the published archive summary, not the local file.
The existing `review_server.py` still serves the same UI against its local API.

Regression tests cover summary allowlisting, latest-observation candidate gates,
static assets/project-relative script paths, browser freshness arithmetic,
future/malformed timestamps and real HTTP API reads. The build needs no frontend
package installation. No browser binary was available in the local environment;
rendered mobile UI inspection remains a deployment follow-up, not a passed test.
