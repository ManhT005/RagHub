# Provider assets

Canonical provider assets live in the repository-level `assets/providers/` directory.
The npm start/build/test hooks stage SVGs into the ignored admin-web `.provider-assets/`
directory because Angular requires asset inputs inside its workspace. Angular then copies
them to `assets/providers/` via `apps/admin-web/angular.json`.
Do not duplicate them under an application's `src/assets` or hotlink logos at runtime.

Brand selection uses persisted catalog IDs, never model names, connection labels or runtime types.
Every catalog entry needs a registry entry and a local asset or an explicit generic fallback.
Run `node scripts/check-provider-brand-assets.mjs` after installing admin-web dependencies.

Azure OpenAI and Groq use text fallbacks until approved vector assets are available.
Cloudflare uses a generic cloud icon. These are placeholders, not official brand marks.
Coming Soon providers remain disabled; adding their visual identity does not enable runtime support.
