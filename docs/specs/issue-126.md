# Spec: Push Lambda cold start hits the 10s init limit (#126)

## Problem

The web push Lambda (`atwood-<env>-web-push`) is a Docker image function running
on the default 128 MB of memory. A cold start in staging timed out at the 10 s
init limit (`Init Duration: 9999.50 ms ... Status: timeout`) and only succeeded
on a retry. Another cold start took 5.9 s. Three things slow it down. Lambda
gives a function CPU in proportion to its memory, so at 128 MB there is very
little CPU for importing `cryptography` and `pywebpush`. The VAPID key is read
from SSM at import time. The Dockerfile installs `pywebpush` and `boto3`
unpinned. The first alert after a quiet period is the one that matters, because
releases sell out within minutes, so it has to arrive within seconds.

## Scope

In scope:
- `atwood_monitor/lambdas.py` (`create_web_push_lambda`): set `memory_size`.
- `lambda/lambda-docker/Dockerfile` and a new `lambda/lambda-docker/requirements.txt`
  that pins the dependencies.
- `lambda/lambda-docker/web_push_lambda.py`: load the VAPID key lazily and cache it.
- Tests in `tests/test_web_push_lambda.py` and a new CDK assertion test.

Out of scope:
- Option (b), moving to a zip function or a layer (reasons below).
- `layer/requirements.txt`, `atwood_monitor/storage.py`, any table, and any
  construct ID or `function_name`.
- Changing the root `requirements.txt` pin (`pywebpush==1.14.0`, which is only
  used by local tests). See Open questions.
- Provisioned concurrency or SnapStart. Both cost money all the time, and
  SnapStart doesn't support container images.
- Changes to the push payload or headers, and anything else from #118.

## Design

**Approach: option (a). Raise memory, keep Docker.** Option (b) changes the
function's `PackageType` from `Image` to `Zip`. CloudFormation can only make
that change by replacing the function. Because `function_name` is fixed
(`f"{prefix}-web-push"`), it would create the new function under the same name
before deleting the old one, so the deploy would fail with a name collision.
Getting round that means renaming or replacing the function, which the issue
and the CLAUDE.md guardrails forbid. Option (c) includes (b), so it is ruled
out for the same reason.

**1. Memory (`atwood_monitor/lambdas.py`)**
- Add `memory_size=512` to the `DockerImageFunction` in
  `create_web_push_lambda`. Change nothing else: keep the construct ID
  `"WebPushLambda"`, `function_name`, `timeout=30s`, the environment, the IAM
  statements and the SNS subscription.
- Why 512 MB: Lambda gives a function one full vCPU at 1,769 MB, so 128 MB gets
  about 7% of a vCPU and 512 MB about 29%, roughly four times as much. Init is
  CPU-bound (importing `cryptography`, `pywebpush` and `requests`). Four times
  the CPU, plus no SSM round trip and no duplicate `boto3`, should bring the
  6 to 10 s init down to well under 2 s. 512 MB also gives about four times
  headroom over the 115 MB currently used. If the staging check below still
  shows an init of 2 s or more, raise it to 1024 MB in the same PR.
- This is an in-place update of `MemorySize`, not a replacement. **Call it out
  at the top of the PR description anyway**, and confirm that the CI
  `cdk diff` shows `[~]` (modify) and not `[-]/[+]` for `WebPushLambda`.

**2. Pinned dependencies (`lambda/lambda-docker/`)**
- Add `requirements.txt` with exact `==` pins: `pywebpush==2.5.0` and the
  versions it resolves to on Python 3.11 / linux x86_64 for each transitive
  dependency it pulls in, at least `cryptography`, `py-vapid`, `http-ece` and
  `requests`. If 2.x also pulls in `aiohttp`, pin that and its dependencies
  too. To get the pins, run `pip install pywebpush==2.5.0` in a clean 3.11
  venv and copy the result of `pip freeze`. Use `cryptography` 42 or later so
  the `curve must be an EllipticCurve instance` breakage from 1.14.x can't
  come back.
- Dockerfile: `COPY requirements.txt .` then
  `RUN pip install --no-cache-dir -r requirements.txt -t ${LAMBDA_TASK_ROOT}`.
- **Drop `boto3`.** The `public.ecr.aws/lambda/python:3.11` base image already
  includes boto3. Installing a second copy into the task root makes the image
  bigger and shadows the runtime's copy, for no gain. The function only uses
  DynamoDB `scan`/`delete_item`, CloudWatch `put_metric_data` and SSM
  `get_parameter`, which every boto3 version supports.
- pywebpush 1.x to 2.x: the handler calls
  `webpush(subscription_info=, data=, vapid_private_key=, vapid_claims=, headers=, ttl=)`
  with a raw key string and reads `WebPushException.response.status_code`.
  The coder must check these against the 2.5.0 source or changelog. As far as
  we know they are unchanged, so no code change is expected. If any of them
  did change, adapt the handler and note it in the PR.
- Do not add anything to `layer/requirements.txt`.

**3. Lazy VAPID key (`web_push_lambda.py`)**
- Remove the module-level `VAPID_PRIVATE_KEY = get_vapid_private_key()`.
- Add a module cache `_vapid_private_key: Optional[str] = None`.
  `get_vapid_private_key()` returns the cached value if it is set. Otherwise it
  resolves the key (the `VAPID_PRIVATE_KEY` env var first, then the SSM
  parameter for the environment, both as today), stores it and returns it.
- `lambda_handler` calls `get_vapid_private_key()` once per invocation, before
  the subscription loop, and passes the result to `webpush`.
- The module-level `boto3.client("ssm")` can stay, because creating a client
  makes no network call. Importing the module must make **no** SSM API call.
- Keep it mypy-clean (`Optional[str]` and `isinstance` narrowing).

**4. PR description must include**
- Cost impact. x86 Lambda costs about $0.0000167 per GB-second. At 512 MB and
  about 3 s (init plus run) per cold invocation, that is about 1.5 GB-s, or
  about $0.000025, per post. The function only runs when a post is published,
  so the cost is negligible (well under $0.01 a month).
- Staging verification: after the staging deploy, run
  `scripts/send-test-push.sh`, then check the `REPORT` line for
  `atwood-staging-web-push` in CloudWatch Logs. Expect `Memory Size: 512 MB`
  and an `Init Duration` under 2000 ms. A human does this step, not the agent.

## Acceptance criteria

1. With `mock_aws`, no `VAPID_PRIVATE_KEY` env var and no SSM parameter,
   `import web_push_lambda` succeeds and makes no SSM call (today it raises
   `ParameterNotFound`).
2. With `ENVIRONMENT=staging`, no env key and `/atwood/staging/vapid_private_key`
   stored in moto SSM as a `SecureString`, the first `lambda_handler`
   invocation passes that value as `vapid_private_key` to `webpush`.
3. Two `lambda_handler` invocations on the same module instance call SSM
   `get_parameter` exactly once in total. Count the calls with a wrapper
   around `mod.ssm.get_parameter`.
4. When the `VAPID_PRIVATE_KEY` env var is set, it is used and SSM is never
   called.
5. With `ENVIRONMENT=production`, the key is read from `/atwood/vapid_private_key`.
6. The existing tests in `tests/test_web_push_lambda.py` still pass unchanged:
   urgency and TTL, a fresh headers dict for each call, and deletion of a
   subscription that returns 410.
7. A CDK assertion test that synthesises `create_web_push_lambda` in a bare
   `Stack` (a dummy `Table` and `Topic`, `EnvironmentConfig(name="staging", …)`)
   finds exactly one `AWS::Lambda::Function` with `MemorySize: 512`,
   `PackageType: "Image"`, `Timeout: 30` and `FunctionName: "<prefix>-web-push"`.
   Its logical ID must start with `WebPushLambda`.
8. Every line of `lambda/lambda-docker/requirements.txt` is pinned with `==`.
   It includes `pywebpush==2.5.0`, `cryptography`, `py-vapid`, `http-ece` and
   `requests`, and it does not list `boto3`. The Dockerfile installs from this
   file and installs no package by name.
9. `git diff main` doesn't touch `layer/requirements.txt` or
   `atwood_monitor/storage.py`.
10. All the CI checks in CLAUDE.md pass (pytest, black, isort, flake8, mypy).

## Test plan

- `tests/test_web_push_lambda.py`: add tests for criteria 1 to 5.
  `_load()` currently sets `VAPID_PRIVATE_KEY`, so add a variant that doesn't,
  and reset `mod._vapid_private_key` (or re-import) between tests.
- New `tests/test_cdk_web_push.py`: criterion 7, using
  `aws_cdk.assertions.Template`. `DockerImageCode.from_image_asset` doesn't
  build the image at synth time, so the test doesn't need Docker. If it turns
  out that it does, skip the test when Docker isn't available and note this
  in the PR.
- Criterion 8: a small pytest that parses `lambda/lambda-docker/requirements.txt`
  and checks the Dockerfile's `RUN pip install` line.
- Manual check after the staging deploy: see Design section 4.

## Open questions

1. The root `requirements.txt` pins `pywebpush==1.14.0`, which the local tests
   use. The tests only import `WebPushException` and mock `webpush`, so they
   pass either way. Should the root pin also move to 2.5.0, so that tests and
   the image use the same version? The issue doesn't say, so this spec leaves
   it as it is.
2. Should the Docker build run in CI (for example `docker build lambda/lambda-docker`
   in `pr-validation.yml`) so that a bad pin is caught before deploy? The
   agent pipeline can't edit workflows, so that would be a follow-up issue.
