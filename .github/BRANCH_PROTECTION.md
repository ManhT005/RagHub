# GitHub branch protection setup

Files in `.github` define CI and collaboration templates, but repository rules
must be enabled by an administrator in **Settings → Rules → Rulesets** (or in
classic branch protection settings). Configure these rules after the CI workflow
has run once, so its check names are available for selection.

GitHub documentation:

- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches>
- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets>

## `develop` ruleset

Target the `develop` branch and enable:

- Require a pull request before merging; with bypass disabled, this blocks direct pushes.
- Require at least **1 approval**.
- Dismiss stale pull request approvals when new commits are pushed.
- Require review from Code Owners.
- Require all conversations to be resolved.
- Require status checks to pass and select these exact checks:
  - `Backend checks`
  - `Frontend checks`
  - `Docker Compose validation`
  - `Database migration`
- Require branches to be up to date before merging (strict status checks).
- Block force pushes and branch deletion.
- Enable "Do not allow bypassing" unless an emergency maintainer process is documented.

Recommended merge method: squash merge for feature branches, using a
Conventional Commit title.

## `main` ruleset

Target the `main` branch and enable:

- Require a pull request before merging; with bypass disabled, this blocks direct pushes.
- Require **2 approvals** when at least two independent reviewers are available.
- Dismiss stale approvals and require Code Owner review.
- Require all conversations to be resolved.
- Require the same four CI checks listed for `develop`.
- Also require `Pull request policy`; this workflow rejects any PR into `main`
  whose source is not the repository's `develop` branch.
- Require branches to be up to date before merging.
- Block force pushes and branch deletion.
- Enable "Do not allow bypassing" for administrators where operationally feasible.

Recommended merge method: create a merge commit from `develop` to preserve the
release boundary, then tag that commit.

## Optional release hardening

For a larger team, additionally enable one of these controls:

- **Require signed commits** after every contributor has configured SSH or GPG signing.
- Protect a `production` GitHub Environment with required reviewers and use it as
  the approval gate in a future release/deployment workflow.

Do not enable signed commits without onboarding instructions; otherwise valid
release PRs may be blocked unexpectedly.

## Activation notes

- Merge this `.github` configuration into the repository's default branch before
  expecting Dependabot version updates to run.
- Let `CI` and `Pull request policy` run at least once, then select the exact job
  names above as required checks in each ruleset.
