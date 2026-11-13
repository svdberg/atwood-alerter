# Spec: Subscribe endpoint errors are blocked by CORS and leak exception text (#117)

## Problem

`POST /subscribe` (`lambda/subscribe_lambda.py`) returns its 400 (`"Invalid
email"`) and 500 responses with no `Access-Control-Allow-Origin` header and a
plain-text body. Browsers block those responses, so the Elm signup dialog sees a
network error and shows the same "Failed to subscribe." whether the user mistyped
the address or the backend failed. The 500 body is `str(e)`, so internal
exception text goes to the client. Users need a clear, actionable message, and
internal details should go only to CloudWatch.

## Scope

In scope:
- New shared helper `lambda/http_response.py` used by `subscribe_lambda.py` and
  `subscribe_web_lambda.py`.
- `lambda/subscribe_lambda.py`: every response goes through the helper, with a
  JSON body, actionable 400 messages, a generic 500 message and `print` logging.
  Malformed or missing bodies return 400, not 500.
- Frontend: `elm-frontend/src/SignupModal.elm` and `src/Main.elm` read the
  `error` field from failed `/subscribe` responses and show it.
- Tests: `tests/test_lambdas.py` and `elm-frontend/tests/SignupModalTests.elm`.

Out of scope:
- CDK, API Gateway and IAM changes. `atwood_monitor/storage.py` stays untouched.
  The existing `OPTIONS` preflight (`add_cors_options` in
  `atwood_monitor/api_gateway.py`) already works.
- Behaviour changes to `subscribe_web_lambda.py` beyond switching to the shared
  helper. Its 500 still returns `str(e)`; see Open questions.
- Other handlers (`status_lambda`, `admin_*`) keep their own headers.
- Stricter email validation (regex, trimming, normalisation), base64 bodies,
  rate limiting, and rollback of the DynamoDB row when `sns.subscribe` fails.

## Design

**Shared helper.** Every non-Docker Lambda uses `lambda_.Code.from_asset("lambda")`
(`atwood_monitor/lambdas.py`), so each function gets the whole `lambda/`
directory. Sibling imports already work in production: `admin_stats.py` does
`from stats import ...`. This is cleaner than copying `_response` again, and it
needs no layer or CDK change. (The web push lambda has no layer, which is fine
because the helper uses only the stdlib.) Add:

```python
# lambda/http_response.py
def json_response(status_code: int, body: dict) -> dict
```

It returns `{"statusCode", "headers", "body": json.dumps(body)}` with headers
`Access-Control-Allow-Origin: *`, `Access-Control-Allow-Headers: *` and
`Content-Type: application/json`. Don't name the module `http.py`, because that
would shadow the stdlib. In `subscribe_web_lambda.py`, delete `_response` and
call `json_response` instead. Only the new `Content-Type` header changes there.

**`subscribe_lambda.lambda_handler`:**
1. `raw = event.get("body")`. If `raw` is `None` or empty, return 400
   `{"error": "Please enter a valid email address."}`.
2. `json.loads(raw)`. On `json.JSONDecodeError` or `TypeError`, or if the result
   is not a `dict`, return 400 `{"error": "Invalid request body."}`.
3. `email = body.get("email")`. If it is not a `str`, or is empty, or has no
   `"@"`, return 400 `{"error": "Please enter a valid email address."}`.
   Today a non-string email raises `TypeError` and returns 500.
4. Keep the existing `put_item` and `sns.subscribe` calls and the 200 message,
   `{"message": "Subscription requested. Check your email to confirm."}`.
5. Wrap only the AWS calls in `try/except Exception as e`. Log with
   `print(f"subscribe failed: {type(e).__name__}: {e}")`, without the email
   address (PII), and return 500
   `{"error": "Something went wrong. Please try again later."}`.

**Frontend.** `Http.expectString` throws away the body of a non-2xx response
(`BadStatus Int`), so `Main.submit` must use `Http.expectStringResponse`.
- `SignupModal` gains `errorMessage : String -> Maybe String`, which decodes
  `{"error": "..."}` with `Json.Decode.field "error" string` and returns
  `Nothing` on failure or when the string is empty.
- `onSubscribeResult` changes from `Bool` to `Result (Maybe String) () -> State -> State`.
  - `Ok ()` behaves as it does today.
  - `Err (Just m)` sets `Error m`.
  - `Err Nothing` sets `Error "Failed to subscribe. Please try again."`.
- `Main.GotSubscriptionResult` carries `Result (Maybe String) ()`. `BadStatus_`
  maps to `Err (errorMessage body)`. Network, timeout and bad-URL errors map to
  `Err (Just "Couldn't reach the server. Check your connection and try again.")`.
- `SignupModal.onEmailChange` (used by `UpdateEmail`) sets the email and, when
  `statusMsg` is `Error _`, resets it to `Idle`. `Sent` and `Sending` are kept.
- `Main.viewStatusMsg` renders `Error msg` as `"! " ++ msg` and drops the
  hard-coded " Please check the address and try again." suffix. Elm escapes the text, so a server string can't inject
  markup.

No data-model, API-contract or infra changes. The guardrails don't apply: no
`storage.py`, no resource names, no new layer dependency.

## Acceptance criteria

1. Valid email `{"email": "foo@example.com"}` returns 200, the body
   `json.loads` to `{"message": "Subscription requested. Check your email to confirm."}`,
   the user row exists and one SNS subscription exists.
2. `{"email": "bademail"}` returns 400 with body
   `{"error": "Please enter a valid email address."}`.
3. A missing `email` key, `{"email": ""}` and `{"email": 123}` each return 400
   with the same body as AC2.
4. `event` with no `"body"` key, or `"body": None`, returns 400 with an `error`
   key and does not call DynamoDB or SNS.
5. `"body": "not json"` and `"body": "[1,2]"` return 400
   `{"error": "Invalid request body."}`.
6. When `sns.subscribe` raises `Exception("internal-detail-xyz")`, the handler
   returns 500 with body `{"error": "Something went wrong. Please try again later."}`.
   The response body does not contain `internal-detail-xyz`, and the captured
   stdout does.
7. Every response in AC1 to AC6 has the headers
   `Access-Control-Allow-Origin == "*"`, `Access-Control-Allow-Headers == "*"`
   and `Content-Type == "application/json"`.
8. `http_response.json_response(418, {"a": 1})` returns statusCode 418, the
   headers from AC7 and body `'{"a": 1}'`.
9. `subscribe_web_lambda` still returns 200 for a valid subscription and 400
   with `{"error": "Missing endpoint in subscription"}` when the endpoint is
   missing, and both responses have the AC7 headers.
10. Elm: `errorMessage "{\"error\":\"Please enter a valid email address.\"}"`
    returns `Just "Please enter a valid email address."`. `errorMessage "oops"`,
    `errorMessage "{}"` and `errorMessage "{\"error\":\"\"}"` return `Nothing`.
11. Elm: `onSubscribeResult (Err (Just "X"))` sets `statusMsg = Error "X"` and
    keeps the email. `onSubscribeResult (Err Nothing)` sets
    `Error "Failed to subscribe. Please try again."`. `onEmailChange` clears an
    `Error` to `Idle` but leaves `Sent` and `Sending` unchanged. `onSubscribeResult (Ok ())` sets `Sent "Check your email to confirm!"`
    and clears the email.
12. All CLAUDE.md checks pass (pytest, black, isort, flake8, mypy, elm-format).

## Test plan

- `tests/test_lambdas.py`:
  - Extend `test_subscribe_lambda_valid_email` and
    `test_subscribe_lambda_invalid_email` with body and header assertions
    (AC1, AC2, AC7).
  - Add parametrized `@mock_aws` tests for AC3 to AC5.
  - Add an AC6 test that monkeypatches `subscribe_lambda.sns.subscribe` to
    raise and uses `capsys` to check stdout.
  - Add a test for `json_response` (AC8).
  - Add header assertions and a missing-endpoint case to the web lambda test
    (AC9).
  - Consider a small fixture for the repeated Users table and topic setup.
- `elm-frontend/tests/SignupModalTests.elm`: update the two
  `onSubscribeResult` tests to the new signature and add `errorMessage` cases
  (AC10, AC11).
- Screenshots: `visual-preview.yml` covers the frontend diff. No new scenario
  is needed, because the fixture router always returns 200.

## Open questions

- `subscribe_web_lambda.py` also returns `str(e)` on 500, the same leak this
  issue fixes. Should this PR give it the generic message too, or should that
  be a follow-up issue? This spec leaves it unchanged to stay within the
  issue's scope.

## UX/UI

Scope: copy, state handling and a11y of the existing signup modal. No new
components, no layout change.

### Flow and placement

Header "Get notified of new releases", then the email input, the Subscribe
button, then the status line (`viewStatusMsg`, wrapped in
`el [ width fill, Region.announce ]`), then the push section. The error text
renders in that same status slot, below the button. Nothing moves.

### States (email subscribe)

| State | Display | Notes |
|-------|---------|-------|
| Idle | nothing | |
| Sending | `Sending...` (slate), button `Subscribing...` and disabled | unchanged |
| Success | `✓ Check your email to confirm!` (green700), email cleared | unchanged |
| Error, server message | `! <server error>` (red700) | e.g. `! Please enter a valid email address.` |
| Error, no usable message | `! <fallback>` (red700) | see below |
| Empty | n/a | no list is shown |
| Push permission denied | unchanged (`Push permission denied. Allow notifications ...`) | not touched by this change |

The modal stays open on error and the typed email is kept so the user can fix
it in place.

### Copy

Render exactly `"! " ++ msg`, with no suffix. Server strings are shown verbatim:
- 400: `Please enter a valid email address.` / `Invalid request body.`
- 500: `Something went wrong. Please try again later.`

Fallback (no parseable `error` field): `Failed to subscribe. Please try again.`

The neutral wording is used because an address-blaming fallback would be wrong
when the cause is an unreadable 5xx. (Design section and AC11 already use it.)

### 500 vs network failure

Keep them distinct, because the advice differs:
- 500 with a readable body: show the server message ("Something went wrong.
  Please try again later.").
- Network error, timeout or bad URL: show `Couldn't reach the server. Check your connection and try again.`
- A non-2xx status with an unreadable body (e.g. an API Gateway 502/429 HTML or
  gateway JSON with `message`, not `error`): the neutral fallback above.

Implementation shape: keep `Err (Maybe String)` for the body case. For
network, timeout and bad-URL errors, `Main` should pass `Err (Just "Couldn't reach the server. Check your connection and try again.")`.
Only `BadStatus_` with an unparseable body yields `Err Nothing`. Add an Elm test for the
network path if it is easy to isolate.

### Clearing the error

- Resubmit: `submit` sets `Sending`, which replaces the error. No change.
- Editing: `UpdateEmail` currently leaves the error on screen. Change it so
  that, when `statusMsg` is `Error _`, editing the input sets `statusMsg = Idle`.
  Do not clear `Sent` or `Sending`. The stale message then doesn't contradict what
  the user is now typing. Add a test for this.
- Closing the modal already resets `Error` to `Idle`. Keep that.

### Accessibility

- The status wrapper already has `Region.announce` (`aria-live="polite"`). It is
  always in the DOM, so the error is announced when its text appears. Keep the
  wrapper persistent. Don't render it conditionally. Polite is acceptable because
  the user has just pressed Subscribe and is waiting on this region. Don't add a
  second `role="alert"`, because that would announce twice.
- Focus: leave focus on the Subscribe button after an error (don't steal it).
  Pressing Enter in the input still resubmits. Optionally the coder may move
  focus back to `#signup-email` on error. That is not required, and the
  live-region announcement is the primary cue.
- Don't rely on colour alone: the `!` prefix stays (`✓` for success).
  `red700` on white is above 4.5:1 and matches the push-denied message.
- Text is rendered through `Element.text`, so server strings are escaped. Long
  messages wrap inside `paragraph` with no overflow.

### Responsive

No change. The status line is full width in the modal, and `paragraph` wraps on
narrow mobile viewports. The longest message ("Couldn't reach the server.
Check your connection and try again.") wraps to two lines at 320px. Verify
there's no horizontal overflow in the review screenshots.

### Screenshots

The fixture router always returns 200, so no scenario is required. If the coder
wants a visual check of the error state, add a fixture `/api/subscribe` 400
returning `{"error":"Please enter a valid email address."}` and a scenario
`signup-dialog-error` in `screenshots/capture.mjs`. This is optional.
