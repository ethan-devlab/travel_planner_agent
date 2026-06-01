# Owner B/C Commit Guide

This guide covers the exact Git flow for Owner B and Owner C:
`pull -> checkout branch -> add upstream -> commit -> push -> pull request`.

## 1. One-time remote setup

Run this once after cloning your fork.

```bash
git remote -v
git remote add upstream https://github.com/<ORIGINAL_OWNER>/<ORIGINAL_REPO>.git
git remote -v
```

Expected result:
- `origin` points to your fork.
- `upstream` points to the main shared repository.

## 2. Sync latest code before starting work

```bash
git checkout main
git fetch upstream
git pull upstream main
git push origin main
```

## 3. Create and switch to your feature branch

Use a branch name with owner + scope.

```bash
git checkout -b owner-b/<feature-name>
# or
git checkout -b owner-c/<feature-name>
```

Examples:
- `owner-b/review-tool-risk-signals`
- `owner-c/calendar-delete-ownership-check`

## 4. Work and commit

```bash
git status
git add <file1> <file2>
git commit -m "feat(owner-b): add explicit itinerary review confirmation flow"
```

Commit message format:
- `feat(owner-b): ...`
- `fix(owner-b): ...`
- `feat(owner-c): ...`
- `fix(owner-c): ...`

## 5. Push branch to your fork

First push:

```bash
git push -u origin owner-b/<feature-name>
# or
git push -u origin owner-c/<feature-name>
```

Later pushes:

```bash
git push
```

## 6. Keep your feature branch updated (recommended)

```bash
git fetch upstream
git rebase upstream/main
git push --force-with-lease
```

Use `--force-with-lease` only after a rebase on your own feature branch.

## 7. Open pull request

From GitHub UI:
- Base repository: `upstream` repo
- Base branch: `main`
- Compare branch: your `owner-b/...` or `owner-c/...` branch on `origin`

Or with GitHub CLI:

```bash
gh pr create --base main --head owner-b/<feature-name> --title "<short title>" --body "<summary>"
# or
gh pr create --base main --head owner-c/<feature-name> --title "<short title>" --body "<summary>"
```

## 8. Pre-PR checklist

- `git status` is clean.
- Only task-related files are included.
- No secrets, `.env`, or API keys are committed.
- Tests relevant to your changes pass locally.
- PR description includes:
  - what changed
  - why it changed
  - how it was tested
