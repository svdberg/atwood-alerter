# Spec: Move artifact actions off Node 20 (#153)

## Problem

GitHub Actions warns "Node.js 20 is deprecated ... actions/upload-artifact@v4"
in the backend and frontend pipelines. Node 20 actions will stop running once
GitHub removes the runtime, which would break artifact hand-off between jobs
(build → validate → deploy, screenshot capture → publish). Upgrading to the
Node 24 majors (`upload-artifact@v7`, `download-artifact@v8`) removes the warning
and the future breakage.

## Scope

In scope: changing only the `uses:` version on these 7 lines.

| File | Line | Change |
|------|------|--------|
| `.github/workflows/ci-cd.yml` | 172 (`backend-build`) | `upload-artifact@v4` → `@v7` |
| `.github/workflows/ci-cd.yml` | 185 (`frontend-build`) | `upload-artifact@v4` → `@v7` |
| `.github/workflows/ci-cd.yml` | 304 (`staging-outputs`, staging deploy job) | `upload-artifact@v4` → `@v7` |
| `.github/workflows/dependency-update.yml` | 59 (`security-reports`) | `upload-artifact@v4` → `@v7` |
| `.github/workflows/monitoring.yml` | 181 (`health-report-*`) | `upload-artifact@v4` → `@v7` |
| `.github/workflows/visual-preview.yml` | 73 (`screenshots`) | `upload-artifact@v4` → `@v7` |
| `.github/workflows/visual-preview.yml` | 91 (`screenshots`) | `download-artifact@v4` → `@v8` |

Out of scope:
- Any other change to the workflows, including other `with:` inputs, job
  structure, and other action versions. The `download-artifact@v8` uses that
  already exist stay as they are.
- **Guardrail:** `ci-cd.yml:304` is inside the staging deploy job. CLAUDE.md says
  not to touch deploy jobs unless the issue asks. The issue asks to fix the
  pipeline warning, so changing only this `uses:` line is allowed. Nothing else
  in any deploy job (credentials, steps, env) may change. Mention this in the PR
  description.
- Python, Elm, CDK, `storage.py`, `layer/requirements.txt`, `scripts/*-policy.json`.

## Design

This is a version bump only. The existing `with:` inputs work unchanged with the
new majors:

- **Inputs used:** `name`, `path` (single and multi-line), `retention-days`
  (upload). `name` and `path` (download). All are still supported in upload v7
  and download v8.
- **Hidden files:** `include-hidden-files` has defaulted to `false` since
  upload v4.4, so the runner already runs with that default. Behaviour does not
  change. (`elm-frontend/` dotfiles are already excluded today.)
- **upload v7 `archive` input:** new, defaults to `true` (zip as before). Leave it
  unset.
- **download v5+ path change:** only affects downloads by `artifact-ids`. All
  downloads here are by `name` or `pattern`, so they still extract into `path`
  (or the workspace) as before. `merge-multiple` (monitoring.yml:199) is
  unchanged and doesn't need editing.
- **Compatibility already proven:** `ci-cd.yml` and `monitoring.yml` already
  download artifacts with `@v8` that `@v4` uploaded. Both use the same
  artifact backend, so mixed versions during rollout are fine.
- **Runner:** the Node 24 majors need Actions runner ≥ 2.327.1. All jobs use
  GitHub-hosted `ubuntu-latest`, which meets this.

No data-model, API or infra impact.

## Acceptance criteria

1. `grep -rn "actions/upload-artifact@v4\|actions/download-artifact@v4" .github/workflows/`
   returns nothing.
2. Each of the 6 upload steps listed in Scope uses `actions/upload-artifact@v7`.
   The `visual-preview.yml` download step uses `actions/download-artifact@v8`.
3. `git diff main -- .github/workflows/` shows only those 7 `uses:` lines
   changed. All `with:` inputs (`name`, `path`, `retention-days`) are identical.
4. Every changed workflow file still parses as YAML
   (`python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml`).
5. The only files changed are the 4 workflow files and `docs/specs/issue-153.md`.
6. The CLAUDE.md checks (pytest, black, isort, flake8, mypy) still pass.
7. On the PR, the `pr-validation.yml` / `ci-cd.yml` runs have no
   "Node.js 20 is deprecated" annotation for the artifact actions. The
   `visual-preview.yml` run still posts screenshots if the PR touches the
   frontend. (Checked manually on the PR, not in a test.)

## Test plan

- No new pytest or Elm tests: there is no code change.
- Run criterion 1's grep and criterion 4's YAML parse locally before committing.
- Run the standard CLAUDE.md check commands to confirm nothing else regressed.
- Reviewer checks the CI run annotations on the PR (criterion 7). Jobs that only
  run on `main`, on a schedule or on dependency updates (deploys, `monitoring.yml`,
  `dependency-update.yml`) are checked after merge.

## Open questions

