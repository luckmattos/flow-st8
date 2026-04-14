# Releasing

## Versioning

- This repository uses Semantic Versioning.
- The canonical version lives in `VERSION`.
- Runtime code reads that value from `version.py`.
- `release-please` updates `VERSION`, `CHANGELOG.md`, the Git tag, and the GitHub Release.

## Day-To-Day Flow

1. Merge changes into `main` using Conventional Commits when possible.
2. `release-please` opens or updates a Release PR.
3. Review that PR like any other change.
4. Merge the Release PR when you're ready to publish.
5. `release-please` creates the tag and GitHub Release automatically.

## Commit Conventions

- `feat:` triggers a minor release.
- `fix:` triggers a patch release.
- `feat!:` or `BREAKING CHANGE:` triggers a major release.
- `chore:`, `docs:`, and similar commit types normally do not trigger a release.

## Manual Overrides

- To force a specific version, add `Release-As: x.y.z` in the commit body.
- To improve generated notes, prefer squash merges with a clean final commit message.

## GitHub Automation

- `.github/workflows/ci.yml` validates the repo on pushes and pull requests.
- `.github/workflows/release-please.yml` manages Release PRs and GitHub Releases.

## Notes

- If you want CI to run on Release PRs opened by the bot, configure a PAT-based token and wire it into the workflow later.
- The current manifest starts at `0.1.0`, matching the existing `v0.1.0` tag.
