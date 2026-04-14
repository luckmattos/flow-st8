# Releasing

## Versioning

- This repository uses Semantic Versioning.
- The canonical version lives in `VERSION`.
- Runtime code reads that value from `version.py`.

## Release Checklist

1. Update `VERSION`.
2. Add a new entry to `CHANGELOG.md`.
3. Commit the release prep.
4. Create an annotated tag like `v0.1.0`.
5. Push the commit and tag to GitHub.

## Commands

```powershell
git add VERSION CHANGELOG.md
git commit -m "chore: release v0.1.0"
git tag -a v0.1.0 -m "flow-st8 v0.1.0"
git push origin main
git push origin v0.1.0
```

## GitHub Automation

- `.github/workflows/ci.yml` validates the repo on pushes and pull requests.
- `.github/workflows/release.yml` creates a GitHub Release automatically when a `v*` tag is pushed.
