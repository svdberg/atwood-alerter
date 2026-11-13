# Spec: Email alerts arrive as raw JSON (#116)

## Problem

`notify_subscribers` in `lambda/lambda_function.py` publishes
`json.dumps({"title", "body", "url"})` to the notify SNS topic with the fixed
subject `New Blog Post`. SNS email delivers that string as-is, so email
subscribers get raw JSON. Email subscribers need a readable alert: a subject
that names the release and a plain-text body. The web push Lambda
(`lambda/lambda-docker/web_push_lambda.py`) subscribes to the same topic. It
runs `json.loads(record["Sns"]["Message"])`, so it must keep getting JSON.

## Scope

In scope:
- `lambda/lambda_function.py`: publish one SNS message per protocol
  (`MessageStructure="json"`) and build a readable subject.
- `tests/test_lambdas.py`: tests for each protocol payload and the subject.

Out of scope:
- SES or HTML email, and email templates.
- Adding `image_url` (or any new key) to the push payload. Follow-up issues
  will do that.
- Any change to `lambda/lambda-docker/web_push_lambda.py`, `atwood_monitor/`
  (CDK, `storage.py`), `layer/requirements.txt` or `elm-frontend/`.
- Changing the `is_sold` heuristic or the stats recording added in #114.

## Design

All changes are in `lambda/lambda_function.py`. Add pure helper functions so
that tests can call them without SNS:

- `SUBJECT_PREFIX = "New Atwood release"` and `MAX_SUBJECT_LEN = 99`.
- `build_push_payload(post) -> dict`: returns exactly
  `{"title": "New Blog Post!", "body": post["title"], "url": post["url"]}`.
  This is the same as today. It is a dict-building function so that a later
  `image_url` key is a one-line change.
- `build_email_subject(title: str) -> str`: sanitises the title to fit SNS
  `Subject` rules (ASCII printable, no line breaks or control characters,
  1 to 99 characters; SNS requires fewer than 100):
  1. `unicodedata.normalize("NFKD", title)`, then `.encode("ascii", "ignore")`,
     so that "Café" becomes "Cafe" and emoji are dropped.
  2. Replace each run of whitespace or control characters (including `\r`,
     `\n`, `\t`) with a single space, then strip.
  3. If the result is empty, return `"New Atwood release"`. Otherwise use
     `f"{SUBJECT_PREFIX}: {clean}"`.
  4. If the subject is longer than 99 characters, cut it to 96 characters,
     strip trailing spaces and add `"..."`. The result is at most 99
     characters.
- `build_email_body(post) -> str`: plain text with Unicode allowed and the
  original title kept:
  ```
  New Atwood release: <title>

  <url>

  Status: Available
  ```
  The status line is `Status: Sold out` when `post.get("sold")` is truthy.
  Otherwise it is `Status: Available`. A missing `sold` key counts as
  available, because the scraper always sets it but test fixtures may not.
  The URL is on its own line with nothing else on that line.
- `build_sns_message(post) -> str`: returns
  `json.dumps({"default": push_json, "email": email_body, "lambda": push_json})`,
  where `push_json = json.dumps(build_push_payload(post))`. `default` is
  required by SNS. It carries the JSON payload, so any protocol without its
  own key gets the same payload as before this change.
- `notify_subscribers(post)` calls `sns.publish(TopicArn=...,
  Subject=build_email_subject(post["title"]), Message=build_sns_message(post),
  MessageStructure="json")`. The error handling and the
  `count_email_subscriptions` / `record_notification` flow do not change.

Web push compatibility: with `MessageStructure="json"`, SNS sends the `lambda`
value as `Records[].Sns.Message`. The CDK `LambdaSubscription` in
`atwood_monitor/lambdas.py` does not use raw delivery. The web push Lambda
therefore still gets a JSON string with `title`, `body` and `url`, and it
needs no change.

Guardrails: no `storage.py`, stack or resource-name changes. No new
dependencies, because `unicodedata` is in the standard library. There is no
infra or API impact.

## Acceptance criteria

1. `notify_subscribers(post)` calls `sns.publish` exactly once, with
   `MessageStructure="json"` and the topic ARN from `NOTIFY_TOPIC_ARN`.
2. The published `Message` parses as JSON with exactly the keys `default`,
   `email` and `lambda`, and every value is a string.
3. `json.loads(message["lambda"])` equals
   `{"title": "New Blog Post!", "body": post["title"], "url": post["url"]}`.
4. `json.loads(message["default"])` equals the same dict as criterion 3.
5. `message["email"]` contains the post title. It contains `post["url"]` as a
   line of its own (`post["url"] in body.splitlines()`) and is not valid JSON.
6. `message["email"]` contains `Status: Available` when `sold` is `False` or
   missing, and `Status: Sold out` when `sold` is `True`.
7. For `title="Spring drop"`, `Subject == "New Atwood release: Spring drop"`.
8. For a title of 200 characters, the subject is at most 99 characters (`len(subject) < 100`),
   starts with `"New Atwood release: "` and ends with `"..."`.
9. For a title with non-ASCII characters, newlines or tabs (for example
   `"Café\nPry-Bar 🔪\tdrop"`), the subject is ASCII-only, has no characters
   below `0x20` and none equal to `0x7f`, and has no double spaces. It
   equals `"New Atwood release: Cafe Pry-Bar drop"`.
10. For a title that is empty or only non-ASCII (for example `"🔪🔪"`), the
    subject is `"New Atwood release"`.
11. Feeding `message["lambda"]` as `Records[0].Sns.Message` into the parsing
    logic of `web_push_lambda` (that is, `json.loads`) returns the expected
    `title`, `body` and `url`. Criterion 3 already covers this, so no Docker
    Lambda import is needed.
12. The existing tests (`test_notify_subscribers_records_stats`,
    `..._publish_failure_writes_nothing`, `..._swallows_stats_failure`) still
    pass. moto accepts the publish, which shows that `default` is present.

## Test plan

Add tests to `tests/test_lambdas.py`. They reuse `_scraper_env()` under
`@mock_aws`, and they capture `publish` kwargs with the existing spy pattern
(wrap `mod.sns.publish` and record the kwargs):
- `test_notify_subscribers_publishes_per_protocol_message`: criteria 1 to 5
  and 7.
- `test_email_body_sold_status`: parametrized over `sold` True, False and
  missing (criterion 6). It calls `build_email_body` directly.
- `test_email_subject_truncates_long_title` (criterion 8).
- `test_email_subject_sanitises_non_ascii_and_newlines` (criterion 9).
- `test_email_subject_fallback_when_empty`: parametrized over `""` and
  `"🔪🔪"` (criterion 10).
- Run the full suite unchanged for criterion 12.

## Open questions

1. The `sold` flag comes from the `is_sold` heuristic, which reads the last
   two lines of the post. Is `Status: Available` / `Status: Sold out` the
   wording the owner wants, given that the heuristic can be wrong? An
   alternative is `Status: Appears to be sold out`.
2. The spec sends the JSON push payload as `default`, which matches today's
   behaviour for non-email protocols. No other protocols are subscribed
   today, so this is a judgement call: should `default` be the plain-text
   body instead?
