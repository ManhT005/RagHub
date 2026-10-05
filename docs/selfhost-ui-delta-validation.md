# Self-host UI delta validation — 2026-10-04

Implemented on `feature/selfhost-ui-v1` against the sidebar/provider delta plan and `selfhost-update-UI/anh2.png`.

## Shared assets

Provider SVGs, source attribution and maintenance instructions live in the repository-level `assets/providers/` directory. Angular stages these into the ignored `apps/admin-web/.provider-assets/` directory through its npm lifecycle hooks. Both development and Docker production builds publish them at `assets/providers/` without remote image requests.

## Workspace behavior

- Workspace navigation shows its name and slug, a separate back action, and permission-filtered administration links. Global account/system links remain in the global scope.
- Provider catalog identity survives connection creation/editing, model registration and workspace summaries. A custom compatible connection stays compatible even when its endpoint is OpenAI.
- Documents have combined search/type/status filters, chronological/name sorting, processing progress, drag-and-drop uploads and information/content tabs.
- The embedding picker filters registered, healthy models by category, provider and name. Changing a model requires reviewing impact and explicit confirmation, then rebuilds the workspace index.
- Switching between upload and model dialogs preserves selected files and waits for modal closing animations.
- TXT/Markdown content renders as escaped plain text. PDF content uses a locally created, authenticated blob with an explicit PDF MIME type and the browser's native viewer; original download remains available when native viewing is unavailable.

The existing ingestion pipeline controls chunking at 450 tokens with 80-token overlap. The reference's configurable chunk strategy, model quality/speed ratings and configuration-only model change are not supported by the current API, so the screen displays actual pipeline settings and uses full reindexing.

## Validation

- Frontend: **122 tests passed across 23 files**; Angular production build passed within the existing bundle budget.
- Backend: the full non-integration suite passed (384 tests), followed by the updated provider identity/contract suite (12 tests).
- Brand asset check: all 11 catalog entries have local assets or explicit fallbacks; no remote image sources.
- PostgreSQL snapshot clone: migration upgrade, downgrade and re-upgrade passed; legacy model IDs, secrets, workspace bindings and grants were preserved and provider identities backfilled. Catalog identity uses migration `20261004_0016` because `0015` already exists for document metadata.
- Docker production image and self-host Compose build/config checks passed.
- Browser acceptance against `raghub-selfhost-test`: eight screens at each of 1024/1440/1920px, mobile/tablet at 390/768px, dark mode, local logos, custom provider creation/editing, provider/model registration, upload and ingestion polling, plain-text preview, original download, confirmed model migration, document deletion and delegated permission guards passed without console/page errors.
- An additional real PDF upload/download check confirmed the authenticated PDF blob loads into Edge's native embedded viewer. Automated screenshots do not assert the native viewer's internal rendering.

Local screenshots are stored under the ignored `.backups/ui-validation/screenshots/` directory. The test UI is served at `http://localhost:18082`; no production publication or remote Git push is included.

## Follow-up feedback

- Kept all existing routes. Merged the four overview cards into one full-width summary strip containing the embedding model, documents/chunks, members and latest indexing information. The strip adapts within one container at narrower widths.
- Removed the organization/domain picker from the active workspace and user management screens and removed the redundant administration-scope table column. Console pages consistently resolve the existing authorized session scope, falling back to the bootstrap `raghub` organization for a fresh session. Existing organization data is retained.
- System admin can create, edit and delete workspaces from the aggregate list. Delegated users cannot trigger these actions; focused regression tests cover both roles and initialization with old test organizations.
- Added semantic theme colors for buttons, headings, overlays, menus, table hover, pagination, tags, alerts, form controls and calendar panels. Adjusted secondary text, sidebar dividers and active link colors for readability in both modes.
- The feedback browser check (`--layout-only`) passed 24 desktop page/width combinations, mobile/tablet layouts, 10 screens in both themes with computed text-contrast checks, real creation/deletion of a temporary workspace and dark upload/model/detail overlays without console errors. The revised workspace/user/guard unit tests passed (16 tests); other frontend tests passed in the full run.
