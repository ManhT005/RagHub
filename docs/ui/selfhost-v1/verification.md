# Self-host UI v1 verification

Acceptance run: 2026-10-04 on `feature/selfhost-ui-v1`, Windows host with Docker
Compose project `raghub-selfhost-test`. The source-built gateway is available at
`http://localhost:18082`; login uses the previously provisioned owner account.
The test suite creates separate organizations/workspaces and delegated users.
Credentials, fixture state, dumps and screenshots stay in ignored local files.

## Results

| Gate | Result |
| --- | --- |
| Backend unit/HTTP/core architecture | 380 passed; 15 live integration tests excluded from this run. |
| Existing backend live integration | 15 passed, including actual ingestion, retrieval, reindex, conversation and widget HTTP paths. |
| Angular component/API/guard regression | 108 passed across 21 files. |
| Angular production image | Build passed; initial bundle 1.13 MB within the existing budget. |
| Widget loader/demo Node regression | 4 passed. |
| Installed core wheel isolation | 59 wheel modules imported with host/runtime imports blocked; cold tokenizer and fake-port lifecycle passed. |
| Migration clone | Upgrade 0012 to 0015, downgrade to 0012 and repeat upgrade passed; five model IDs, ciphertext, bindings and legacy grants preserved. |
| Live UI API smoke | Passed with actual Sentence Transformer inference and Ollama `gemma3:1b`, document detail/download/search, delegated direct 403s, model binding and private/public streaming chat with citation. |
| Queue failure recovery | Redis outage produced QUEUE_FAILED, old active index continued serving search; restoring Redis and retrying completed atomic activation. |
| Browser acceptance | Eight screens at 1024/1440/1920 px without page overflow; provider manual registration, upload/polling/detail, original download, cancelled/confirmed deletion, embedding migration, delegated navigation and direct URL denial passed. Drawer/modal content overflow checks passed. No console/unhandled page errors. |

Cloud adapter discovery/registration/error sanitization are covered by deterministic
backend tests. No live Gemini/OpenAI paid account was used; live AI checks use local
Sentence Transformer and Ollama. The queue-outage scenario was run only on the
explicit local test project. The ordinary API smoke also passed independently
with Redis available.

## Reproduce

From the repository root, using an installed backend test environment:

```powershell
.venv/Scripts/python.exe -m pip install -r backend/requirements.lock
.venv/Scripts/python.exe -m pip install --no-deps -e ./raghub-core -e ./backend
Push-Location raghub-core
../.venv/Scripts/python.exe -m pytest -p no:cacheprovider
Pop-Location
$env:PROVIDER_MASTER_KEY = 'raghub-ci-provider-key-not-for-production'
Push-Location backend
../.venv/Scripts/python.exe -m pytest -m "not integration" -q
Pop-Location
Push-Location apps/admin-web
npm test
npm run build
Pop-Location
node --test apps/chat-widget/tests/loader.test.cjs apps/chat-widget/tests/demo.test.cjs
.venv/Scripts/python.exe -m build raghub-core --outdir .backups/ui-validation/wheels
.venv/Scripts/python.exe -m build backend --outdir .backups/ui-validation/wheels
.venv/Scripts/python.exe scripts/check-core-package.py --wheel .backups/ui-validation/wheels/raghub_core-0.1.0-py3-none-any.whl --backend-wheel .backups/ui-validation/wheels/raghub_backend-0.1.0-py3-none-any.whl
```

Local Compose acceptance commands use the existing test environment and ignored
owner JSON (`email`/`password`). Confirm the gateway/data services/worker are
healthy and Ollama has `gemma3:1b` installed before running:

```powershell
.venv/Scripts/python.exe scripts/check-selfhost-integration.py --env-file .backups/selfhost-validation/runtime.env --project raghub-selfhost-test --owner-file .env.selfhost-owner.json
.venv/Scripts/python.exe scripts/self-host-ui-smoke.py --base-url http://localhost:18082 --owner-file .env.selfhost-owner.json --state-file .backups/ui-validation/ui-state.json
```

The API smoke creates a new isolated organization on every run and writes the
state required by the browser suite. The optional queue-recovery run additionally
requires `--queue-outage --env-file .backups/selfhost-validation/runtime.env
--project raghub-selfhost-test`; it briefly stops Redis and restores it in `finally`.
Run it independently of other tests that use Redis.

Browser tooling is optional verification tooling, not an application dependency:

```powershell
.venv/Scripts/python.exe -m pip install playwright==1.56.0
.venv/Scripts/python.exe -m playwright install chromium --only-shell
.venv/Scripts/python.exe scripts/check-selfhost-ui-browser.py --owner-file .env.selfhost-owner.json --state-file .backups/ui-validation/ui-state.json
```

The browser authenticates against the real API and uses no mocked routes. It
creates a fresh connection/model/file, checks that migration needs confirmation,
waits for terminal processing and verifies the delegated user cannot reach admin
or AI settings. Screenshots are saved under
`.backups/ui-validation/screenshots`, including document detail and embedding
impact at 1024 px. Tables may scroll horizontally inside their containers.

Migration verification on a pre-UI database:

```powershell
.venv/Scripts/python.exe scripts/check-ui-migrations.py --env-file .backups/selfhost-validation/runtime.env --project raghub-selfhost-test
```

After the source database has been upgraded, supply its retained pre-UI dump:

```powershell
.venv/Scripts/python.exe scripts/check-ui-migrations.py --env-file .backups/selfhost-validation/runtime.env --project raghub-selfhost-test --snapshot .backups/ui-validation/before-ui-migrations.dump
```

This script restores into a uniquely named clone, migrates only that clone,
verifies the source revision remains unchanged, and drops only the clone it
created. It refuses a snapshot that is not at `20261003_0012`. It does not replace
an existing pre-UI backup when the live source is already upgraded.

## Commit review

| Commit | Part |
| --- | --- |
| `d499dbc` | Frozen contracts and reference-asset exclusion. |
| `40359fd` | Workspace authorization foundation and frontend gates. |
| `ea8bbb9` | Provider connections, encrypted credentials, discovery and registry. |
| `3422d6b` | Provider onboarding and registry screens. |
| `17c354c` | Workspace summaries, document metadata and safe model endpoints. |
| `7bd5a36` | Active metadata and pending-index protection. |
| `1f4ab5d` | Workspace shell, pages, document and chat flows. |
| `b8ee6ba` | Browser-found drawer/metadata fixes, workspace request isolation and permission-revocation regression. |

Later commits contain browser-found fixes and these reproducible acceptance tools.
Review the complete branch with `git log --oneline refactor/core-package..HEAD`.
Rollout/rollback behavior and deferred scope: [implementation.md](implementation.md).
