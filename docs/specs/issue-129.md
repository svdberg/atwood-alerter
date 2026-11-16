# Spec: Remove permanently failing push subscriptions (#129)

## Problem

`lambda/lambda-docker/web_push_lambda.py` deletes a subscription only when the
push service answers 404 or 410. Subscriptions that fail for good with a 400 or
403 stay in the table. On staging, Apple returns `400 {"reason":"VapidPkHashMismatch"}`
for an old subscription, and it fails on every alert. Each dead entry costs one
request and one `PushFailure` per alert, and it delays the subscribers after it
because the loop is sequential. The log line also hides the reason. The
`ttl_seconds` attribute written by `subscribe_web_lambda.py` doesn't match the
table's TTL attribute (`ttl`), so items never expire either.

## Scope

In scope:
- `lambda/lambda-docker/web_push_lambda.py`: classify failures, delete only
  confirmed-dead subscriptions, log status and reason, add a deletion metric,
  and keep going after network errors.
- `lambda/subscribe_web_lambda.py`: stop writing `ttl_seconds` (the TTL decision is below).
- Tests in `tests/test_web_push_lambda.py` and `tests/test_lambdas.py`.

Out of scope:
- `atwood_monitor/storage.py` and every other CDK file. Table config, TTL
  attribute and resource names stay as they are.
- Frontend (`elm-frontend/`), scan pagination, parallel sending, request
  timeouts for `webpush()`, and showing the new metric in `admin_stats.py`.
- Cleaning up existing items. Old dead entries are deleted the next time an
  alert goes out.

## Design

### 1. Failure classification (`web_push_lambda.py`)

Add a pure helper, `classify_failure(status_code, body) -> tuple[str, str | None]`,
that returns `(action, reason)`. `action` is one of `"delete"`,
`"delete_if_confirmed"` or `"keep"`.

- **Extract the reason** with a separate helper,
  `extract_reason(body: str | None) -> str | None`. It parses JSON and takes
  the first value it finds in this order: top-level `reason` (Apple),
  `error.details[*].errorCode` (FCM v1), `error.status` (FCM), top-level
  `error` when it is a string, then `message`. A body that is empty, `None`, not
  JSON or not an object gives `None` and never raises.
- **Rules:**
  - 404 or 410: `"delete"`, whatever the body says. This is today's behaviour.
  - 400 or 403 with a reason in `SUBSCRIPTION_DEAD_REASONS`:
    `"delete_if_confirmed"`. Compare case-insensitively after removing `_`,
    `-` and spaces. The set is `VapidPkHashMismatch`, `BadDeviceToken`,
    `Unregistered`, `ExpiredSubscription`, `InvalidRegistration`
    (so `UNREGISTERED` and `invalid-registration` match too).
  - Everything else is `"keep"`: 400 or 403 with an unknown or missing reason,
    reasons that point at our own config (`BadJwtToken`,
    `InvalidProviderToken`, `ExpiredProviderToken`, `MissingProviderToken`,
    `BadWebPushTopic`, `PayloadTooLarge`, `TooManyRequests`, …), 401, 413,
    429, 5xx, and a missing status code. Only a fixed allowlist of reasons
    can lead to a deletion.

### 2. Mass-deletion guard

`VapidPkHashMismatch` is ambiguous. If our VAPID private key were wrong (for
example a bad SSM value), Apple would return it for **every** subscriber. So
the handler doesn't delete `"delete_if_confirmed"` candidates straight away. It
collects them for each SNS record and deletes them after the loop, and only if
at least one push to the **same push-service host** (`urlparse(endpoint).netloc`)
succeeded in that record. A success on another host doesn't count, so an
attacker-registered endpoint can't enable deletions on Apple. A successful push
shows our key and JWT work. For hosts with no success, it logs one line per host,
`Skipping deletion of N subscriptions on <host>: no successful push to that host
to confirm config`, and deletes nothing there. 404/410 deletions stay immediate, as today.

### 3. Logging and metrics

- Every `WebPushException` logs one line with the subscription id, status code,
  the reason (or `none`), the action, and the first 200 characters of
  `ex.response.text`. Use `getattr` because `ex.response` can be `None` or
  have no `text`.
- Each actual `delete_item` call emits `PushSubscriptionDeleted` (namespace
  `WebPushNotifications`, dimension `Environment`, Count 1), next to the
  existing `PushFailure`.
- Catch `requests.exceptions.RequestException` (timeouts, connection errors)
  for each subscription. Log it, emit `PushFailure`, keep the subscription and
  carry on with the next one. Today a single timeout ends the whole loop.
  `requests` is already pinned in `lambda/lambda-docker/requirements.txt`, so
  no new dependency is needed.

### 4. TTL decision: no expiry. Stop writing `ttl_seconds`; leave `storage.py` alone.

Rationale:
- Expiry would delete valid subscriptions. The page re-registers only when it
  loads: `checkExistingSubscription` in `elm-frontend/public/index.html` sends
  `granted`, which makes `PushPermissionResult` in `Main.elm` call
  `subscribeToPush`, which POSTs to `/register-subscription`. Push subscribers
  rely on alerts and may never revisit the site. With a 30-day expiry they would
  silently stop getting alerts. Bumping the TTL after each successful push
  would mean losing anyone who goes 30 days without a release.
- Expiry isn't needed for cleanup anymore. Every alert pushes to every
  subscription, and §1 and §2 delete the ones the push service reports dead,
  which is the reliable signal.
- Writing `ttl` from the Lambda would turn on expiry. Changing `storage.py`
  is a production-data risk (CLAUDE.md guardrail). Dropping the write makes the
  code match the intent with no infra change. The `ttl` setting on the table
  stays but is unused.
- Existing items: DynamoDB ignores `ttl_seconds`, so nothing expires and no
  migration is needed. `put_item` replaces the whole item, so the attribute
  disappears the next time a browser re-registers.
- Add a one-line comment in `subscribe_web_lambda.py` saying that writing `ttl`
  would turn on expiry for this table.

**Guardrails:** no change to `storage.py`, stack or resource names, or `layer/requirements.txt`.

## Acceptance criteria

1. `classify_failure(410, "")` and `classify_failure(404, None)` return `"delete"`.
2. `classify_failure(400, '{"reason":"VapidPkHashMismatch"}')` returns
   `("delete_if_confirmed", "VapidPkHashMismatch")`. The same holds for
   `BadDeviceToken`, `Unregistered` and `ExpiredSubscription` with 400 or 403.
3. An FCM body
   `{"error":{"status":"NOT_FOUND","details":[{"errorCode":"UNREGISTERED"}]}}`
   with 400 or 403 gives `"delete_if_confirmed"`, and so does a body whose
   `error.status` is `"INVALID_REGISTRATION"`.
4. 400 or 403 with `BadJwtToken`, `InvalidProviderToken` or
   `ExpiredProviderToken`, an unknown reason, an empty body, `None`, or non-JSON
   text (`"Bad Request"`) gives `"keep"`, and nothing raises.
5. 429, 500, 502 and 503 give `"keep"` whatever the body says, including
   `{"reason":"Unregistered"}`.
6. Handler: subscription `a` raises 400 `VapidPkHashMismatch` and `b`
   succeeds. After the call only `b` is left, and `PushSubscriptionDeleted`
   was emitted once.
7. Handler: every subscription raises 400 `VapidPkHashMismatch`. All of them
   stay, and `PushSubscriptionDeleted` is not emitted.
8. Handler: 410 for `a` while `b` fails with 500. `a` is deleted and `b`
   stays. The existing `test_handler_deletes_gone_subscription` still passes.
9. Handler: `a` raises `requests.exceptions.Timeout`. `b` is still pushed, both
   subscriptions stay, and `PushFailure` is emitted for `a`.
10. Handler: 400 with `BadJwtToken` for `a` while `b` succeeds. Both stay.
11. Handler: the failure log line (from `capsys`) contains the subscription id,
    the status code and the reason.
12. A `WebPushException` whose `response` is `None` keeps the subscription
    and doesn't raise.
13. `subscribe_web_lambda` writes no `ttl_seconds` and no `ttl` attribute. The
    item still has `subscription_id` and `subscription`.

## Test plan

- `tests/test_web_push_lambda.py`: parametrised unit tests for
  `classify_failure` and `extract_reason` (AC 1–5). Handler tests with moto
  (AC 6–12) use a fake response object with `status_code` and `text`.
  Replace the `put_metric_data` no-op stub with one that records the metric
  names. Use a three-subscription fixture where a test needs one success.
- `tests/test_lambdas.py`: extend
  `test_subscribe_web_lambda_registers_subscription` to assert AC 13.
- Run the full check suite from CLAUDE.md (pytest, black, isort, flake8, mypy).

## Open questions

- Is the FCM error body format for web push endpoints (`fcm.googleapis.com/fcm/send/…`)
  right? FCM sometimes answers with plain text. The parser handles that by
  keeping the subscription, so a dead FCM subscription that only reports
  400/403 with plain text won't be removed. A real staging FCM failure body
  would settle it.
- Should `PushSubscriptionDeleted` appear on the admin stats page
  (`admin_stats.py`)? It is out of scope here.
