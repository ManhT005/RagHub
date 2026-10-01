# Contributing

## Branches

Create work from an up-to-date `develop` branch. Use one of these prefixes:

- `feature/<short-name>` for product work.
- `fix/<short-name>` for defect fixes.
- `chore/<short-name>` for maintenance and tooling.
- `docs/<short-name>` for documentation-only changes.

Merge reviewed work into `develop`. Reserve `main` for release-ready commits.

## Commits

Use Conventional Commits in the form `type(scope): summary`, for example:

```text
feat(ingestion): index PDF pages in Elasticsearch
fix(api): preserve request ID in error responses
chore(compose): pin infrastructure images
```

Keep a commit focused, do not commit secrets, and include tests for changed
behavior where practical.
