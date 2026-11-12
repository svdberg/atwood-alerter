# CLAUDE.md

Guidance for Claude (and other coding agents) working in this repository, both
locally and in the GitHub Actions issue → PR pipeline.

## What this is

Serverless monitor for atwoodknives.blogspot.com: a scheduled Lambda scrapes the
blog's RSS feed, stores new posts in DynamoDB, and notifies subscribers (SNS +
web push). An Elm frontend is served from S3/CloudFront. Infra is AWS CDK (Python).

| Path | Contents |
|------|----------|
| `lambda/` | Lambda handlers (`lambda_function.py` = scraper, `status_lambda.py`, `subscribe_*`, `admin_*`) and `dynamo.py` helpers |
| `atwood_monitor/` | CDK stacks and constructs (`atwood_monitor_stack.py`, `storage.py`, `lambdas.py`, `api_gateway.py`, …) |
| `app.py` | CDK app entry; `ENVIRONMENT=staging\|production` selects the stack |
| `layer/` | Lambda layer requirements; built into `out/layer.zip` by `build-layer-with-docker.sh` |
| `elm-frontend/` | Elm 0.19 + Tailwind frontend (`src/Main.elm`, `tests/`) |
| `tests/` | pytest suite using `moto` to mock AWS |
| `.github/workflows/` | CI (`ci-cd.yml`, `pr-validation.yml`) and agent workflows (`claude*.yml`) |

## Commands

Python 3.11. Install once:

```bash
pip install -r requirements.txt -r tests/requirements.txt black isort flake8 mypy
```

Run before every commit (these mirror CI):

```bash
python -m pytest tests/ -q
black --check .
isort --check-only . --profile black
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=out,cdk.out,elm-frontend/node_modules
mypy lambda/ atwood_monitor/ --ignore-missing-imports
```

Fix formatting with `black . && isort . --profile black`.

Frontend (only when touching `elm-frontend/`):

```bash
cd elm-frontend && npm ci
npx elm-format --validate src/      # or `npx elm-format --yes src/` to fix
```

`elm-frontend/build.sh` and `cdk synth` need AWS credentials and are not
available to agents. CI covers them; don't try to run them.

## Conventions

- PR titles must follow Conventional Commits (`feat:`, `fix:`, `chore:`,
  `refactor:`, `test:`, `docs:`, `ci:` …). `pr-validation.yml` enforces this.
- Black/isort with line length 88 (see `pyproject.toml`).
- New Lambda behaviour needs a test in `tests/` using `moto` (`@mock_aws`);
  tests import handlers by putting `lambda/` on `sys.path`.
- Keep type hints mypy-clean; prefer `isinstance` narrowing over `# type: ignore`.

## Guardrails for agents

- Never push to `main`. Work on a `claude/…` branch and open a PR; a human merges.
- Never touch deploy credentials, `scripts/*-policy.json`, or the deploy jobs in
  `ci-cd.yml` unless the issue explicitly asks for it.
- Changes to `atwood_monitor/storage.py` (DynamoDB tables) or stack/resource
  names can destroy production data. Call these out at the top of the PR
  description.
- Don't add new runtime dependencies to `layer/requirements.txt` without
  saying why in the PR.
- If an issue is ambiguous or too large for one PR, comment on the issue with
  questions or a proposed split instead of guessing.
