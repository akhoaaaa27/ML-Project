# XPECTA on Render

Use one Web Service connected through Git Provider to `akhoaaaa27/ML-Project`. Select `xpecta-refresh-and-scatter` and keep the root directory at the repository root. Connect the GitHub account that can access the repository to enable redeploys on commit. [Render Web Services](https://render.com/docs/web-services) · [Automatic deploys](https://render.com/docs/deploys#automatic-deploys)

| Dashboard field | Value |
| --- | --- |
| Language | Python |
| Build Command | `python -m pip install -r scripts/xpecta_api/requirements.txt` |
| Start Command | `python -m uvicorn scripts.xpecta_api.app:create_app --factory --host 0.0.0.0 --port "$PORT"` |
| Health Check Path | `/api/v1/health/ready` |
| Auto-Deploy | On Commit |
| Environment | `PYTHON_VERSION=3.14.0`, `XPECTA_MODE=REAL_RESEARCH` |

The app accepts the default `onrender.com` hostname that Render sets through `RENDER_EXTERNAL_HOSTNAME`. Render runs in read-only mode. Leave the local `.env`, operator token and `XPECTA_SNAPSHOT*` overrides on your own machine. The deploy reads the version and checksums from `data/history/shared_snapshot.json`. [Render Python versions](https://render.com/docs/python-version) · [Render environment variables](https://render.com/docs/environment-variables)

The repository contains the prepared `web/xpecta/integrated.html` and its frontend assets. When changing the V9.12 source or crests, regenerate the frontend with `scripts.xpecta_api.prepare_frontend` locally, then copy only the generated `integrated.html` over `web/xpecta/integrated.html`. The build checks the reference hash, strips the original demo scripts, and adds `/assets/app.js`. The local source, working files and staging evidence stay in the ignored directory. Python dependencies and the published data are installed or read from the selected commit.

When the deploy is **Live**, open `/api/v1/health/ready` on the Web Service URL. Expect `READY`, `frontend_available: true`, and the `snapshot_version` from the deployed commit. Open `/` and generate a custom matchup to verify real model inference. For official upcoming fixtures, preview availability still follows the verified schedule and history from the selected snapshot. [Render health checks](https://render.com/docs/health-checks)

For later updates, publish a reviewed snapshot and run `share_snapshot` before committing and pushing to the Render-linked branch. [Snapshot sharing workflow](PHASE_9_6_REFRESH_READINESS_REPORT.md#share-an-approved-version-with-the-team-through-git)
