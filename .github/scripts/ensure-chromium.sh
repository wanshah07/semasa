#!/usr/bin/env bash
# Playwright's Chromium on a GitHub runner without making apt a single point of failure. `playwright install --with-deps`
# runs apt-get for the browser's system libraries, and the runner's apt mirrors are sometimes unreachable
# ("Temporary failure resolving azure.archive.ubuntu.com"): the 15:13 and 15:17 UTC scrapes of 11 Nov 2026 each spent about ten
# minutes in apt and then failed, so no scrape ran from 07:17 to the next one. The order:
#   1. download the browser alone (Playwright's own CDN, no apt) and try to launch it: ubuntu-latest already carries most
#      of the libraries, so this normally finishes here
#   2. only if the launch fails, install the system libraries with apt (retried, with a time limit), then launch again
# It exits 1 only when Chromium still cannot be launched at the end, so a genuine problem still fails the job, but an apt
# outage no longer does when the browser can run without it.
set -u
launches() {
  python - <<'PY' 2>/dev/null
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    b.close()
PY
}
timeout 600 python -m playwright install chromium || echo "::warning::playwright could not download chromium"
if launches; then echo "chromium launches without apt"; exit 0; fi
echo "::warning::chromium needs system libraries: installing them with apt"
for attempt in 1 2 3; do
  if timeout 600 sudo env "PATH=$PATH" "$(command -v python)" -m playwright install-deps chromium; then break; fi
  echo "::warning::apt attempt $attempt failed"; sleep 10
done
if launches; then echo "chromium launches"; exit 0; fi
echo "::error::chromium cannot be launched on this runner"
exit 1
