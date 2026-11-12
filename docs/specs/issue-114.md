# Spec: Admin status page with usage statistics (#114)

## Problem

The admin needs to see how the app is used: how many subscribers there are per
channel and how many notifications have gone out. An admin page already exists
(`elm-frontend/admin/index.html`, plain HTML/JS). It logs in with a shared
secret and shows a bare table with two numbers (`users`, `web_push`) from
`GET /admin`. Nothing records notification sends in DynamoDB. The scraper
publishes to SNS and forgets. The web push Lambda only emits the CloudWatch
metrics `WebPushNotifications/PushSuccess` and `PushFailure`. The admin wants
richer numbers shown with clear visuals.

## Scope

In scope:
- Keep the existing auth: the API Gateway `TokenAuthorizer` (`lambda/admin_auth.py`)
  compares the `Authorization` header with the SSM secret. It is already
  "very basic auth". No change.
- Scraper (`lambda/lambda_function.py`, `lambda/dynamo.py`): after a successful
  SNS publish, increment a monthly counter item in the **existing** posts table.
- `lambda/admin_stats.py`: return subscriber counts per type, notification
  totals and a 12-month series. Data comes from DynamoDB, SNS and CloudWatch.
- CDK `atwood_monitor/lambdas.py` and `atwood_monitor_stack.py`: new env vars
  and IAM for the stats and scraper Lambdas.
- Frontend: rewrite the admin page in Elm (`src/Admin.elm`) with stat cards and
  SVG charts. Keep the existing delete feature.
- Screenshot harness: add an admin scenario.

Out of scope:
- Any change to `atwood_monitor/storage.py`. No new tables, no new GSIs.
- Changes to the web push Docker Lambda (`lambda/lambda-docker/`). Push counts
  come from the CloudWatch metrics it already emits.
- Changing the auth mechanism (users, sessions, JWT) or adding rate limiting.
- Backfilling email or post counts from before deploy.
- Known bugs that stay as they are: the web push TTL attribute mismatch
  (`ttl_seconds` written vs `ttl` configured), and admin delete not
  unsubscribing the email from SNS.
- Main page (`src/Main.elm`). No new Elm or npm dependencies.

## Design

### Data model (no `storage.py` change)
Monthly counter items in the posts table, next to the existing `__meta__` item:

| `post_id` | attributes |
|-----------|------------|
| `__stats__#YYYY-MM` (UTC) | `posts_announced` N, `email_recipients` N, `last_sent` S (ISO-8601) |

- In `dynamo.py`, add `record_notification(email_recipients: int, now: datetime)`.
  It does one `update_item` with
  `ADD posts_announced :one, email_recipients :n SET last_sent = :now`.
- In `lambda_function.py`, `notify_subscribers` calls it only after
  `sns.publish` succeeds. `email_recipients` is the number of **confirmed**
  email subscriptions on the topic: page through `list_subscriptions_by_topic`
  and count `Protocol == "email"` where `SubscriptionArn != "PendingConfirmation"`.
  Put this in a helper in `dynamo.py` or a new `lambda/stats.py` so admin_stats
  can reuse it. If counting or recording fails, log the error and swallow it.
  It must never block or undo the notification.
- Safety: these keys can't collide with Blogger post IDs (`tag:blogger.com,…`).
  `is_table_empty` is unaffected because counters are written only after seeding.

### API: `GET /admin` (existing route, same authorizer)
Refactor `admin_stats.py` into `build_stats(now: datetime) -> dict`.
`lambda_handler` calls it with `datetime.now(timezone.utc)`. The response
**keeps** `users` and `web_push` for backward compatibility:

```json
{
  "users": 12, "web_push": 4,
  "subscribers": {"email_confirmed": 10, "email_pending": 2, "web_push": 4},
  "notifications": {"posts_announced": 3, "email_recipients": 28,
                    "push_success": 11, "push_failure": 1,
                    "last_sent": "2026-11-10T18:07:00+00:00"},
  "monthly": [{"month": "2025-12", "posts_announced": 0, "email_recipients": 0,
               "push_success": 0, "push_failure": 0}, "... 12 entries, oldest first"]
}
```
- `users` and `web_push` are `scan(Select="COUNT")`, **paginated** over
  `LastEvaluatedKey`. The current code reads only the first page.
- `subscribers.email_*` come from SNS `list_subscriptions_by_topic`, paginated
  and filtered to `Protocol == "email"`.
- Monthly email and post values come from `batch_get_item` on the 12
  `__stats__#YYYY-MM` keys for the current month and the 11 before it. Missing
  months count as 0.
- Monthly push values: one `cloudwatch.get_metric_statistics` call each for
  `PushSuccess` and `PushFailure`. Use namespace `WebPushNotifications`,
  dimension `Environment = ENVIRONMENT.title()`, `Period=86400`, `Statistics=["Sum"]`
  and a time window covering the 12 months. Bucket the datapoints by month in Python.
- `notifications.*` totals are sums over the 12 months. `last_sent` is the
  latest `last_sent`, or `null`.
- Fault isolation: if SNS fails, the `subscribers.email_*` fields are `null`.
  If CloudWatch fails, the `push_*` fields are `null`. The response is still a 200.
- `Decimal` values from DynamoDB must be converted to `int` before `json.dumps`.

### Infra (`atwood_monitor/lambdas.py`, `atwood_monitor_stack.py`)
- `create_admin_stats_lambda` gains `posts_table` and `notify_topic` params.
  Add env vars `POSTS_TABLE` and `NOTIFY_TOPIC_ARN`, and grants
  `posts_table.grant_read_data`, `sns:ListSubscriptionsByTopic` on the topic
  ARN, and `cloudwatch:GetMetricStatistics` on `*`. CloudWatch read does not
  support resource scoping.
- `create_scraper_lambda`: add `sns:ListSubscriptionsByTopic` on the topic. The
  scraper already has read/write on posts.
- Update the call sites in `atwood_monitor_stack.py`. No resources are renamed
  or added. Note that all Lambdas except web push share `lambda_role`, so grants
  apply to the whole role. That matches today's behaviour. Mention it in the PR.

### Frontend
- New `src/AdminStats.elm` (pure, no ports): `Stats` types, `statsDecoder`
  (nullable fields → `Maybe Int`), and chart helpers. The helpers are
  `barHeights : Float -> List Int -> List Float` (scale to max height; all zero
  → all 0, never NaN) and `failureRate : Int -> Int -> Maybe Float`.
- New `src/Admin.elm` (`Browser.element`, imports `Config.apiBaseUrl`):
  - Login form: a password input labelled "Admin secret" and a "Log in" button
    (Enter submits). The secret lives in the model only, never in
    localStorage. "Log out" clears it.
  - `GET {apiBaseUrl}/admin` with header `Authorization: <secret>`. API Gateway
    deny responses carry no CORS headers, so the browser reports
    `NetworkError`. Treat any error as "Login failed or API unreachable".
  - Dashboard:
    - Stat cards for email confirmed, email pending, web push, posts
      announced, emails sent, push delivered, and push failure rate.
      `null` shows as "—".
    - A subscriber-mix chart: a horizontal stacked bar or donut.
    - A 12-month grouped bar chart of emails sent and push delivered.
    - "Last notification" date.
    - A "Refresh" button.
  - Draw charts with `Svg.Styled` from `rtfeldman/elm-css`, which is already
    a dependency. Each chart `<svg>` has `role="img"` and an `aria-label`
    summary. Style with Tailwind / elm-ui to match `Main.elm`.
  - Delete section: same behaviour as today. `DELETE /admin` with body
    `{"email": id, "subscription_id": id}` shows the result and then refreshes
    the stats.
- `admin/index.html` becomes a shell: a mount `<div>`, `<script src="admin.js">`
  and `Elm.Admin.init`. Remove the inline JS.
- `build.sh`: add `npx elm make src/Admin.elm --output=dist/admin/admin.js --optimize`
  after `Config.elm` is generated (inside the existing trap). Keep copying
  `admin/index.html`.
- `screenshots/capture.mjs`: add an `admin` scenario. It navigates to
  `/admin/index.html`, fills the secret, clicks "Log in" and waits for the
  dashboard. Add a route that returns `fixtures/admin.json` for `/api/admin`
  (GET). Add a realistic `fixtures/admin.json` with non-zero months and one
  `null` field.

## Acceptance criteria

1. In `notify_subscribers`, a successful publish creates or increments
   `__stats__#<current UTC YYYY-MM>` in the posts table: `posts_announced` +1,
   `email_recipients` + the confirmed email subscription count, `last_sent` set.
2. Pending-confirmation email subscriptions and the Lambda subscription are not
   counted in `email_recipients`.
3. If `sns.publish` raises, no stats item is written.
4. If recording stats raises, `notify_subscribers` does not raise and the
   publish still happens.
5. `build_stats(now)` returns `users` and `web_push`. The existing
   `test_admin_stats_counts` still passes once its fixtures add the new
   env vars and resources.
6. `subscribers` returns `email_confirmed` and `email_pending` counts from SNS
   that match the topic's email subscriptions.
7. `monthly` has exactly 12 entries, oldest first, ending at `now`'s month.
   Months without a stats item have zeros.
8. Push values in `monthly` match CloudWatch `PushSuccess`/`PushFailure` sums
   for the `Environment` dimension. Datapoints from another environment are
   ignored.
9. `notifications` totals equal the sums of `monthly`. `last_sent` is the
   latest value, or `null` when there is none.
10. If the SNS or CloudWatch client raises, the matching fields are `null` and
    the status is 200.
11. Counts are correct when a scan spans several pages. Test this by
    monkeypatching the table's `scan` to return `LastEvaluatedKey` once.
12. `AdminStats.statsDecoder` decodes `screenshots/fixtures/admin.json`,
    including the `null` field as `Nothing`.
13. `barHeights 100 [0, 5, 10]` gives `[0, 50, 100]`. `barHeights 100 [0, 0]`
    gives `[0, 0]`.
14. `failureRate 0 0 == Nothing`. `failureRate 9 1 == Just 0.1`.
15. `elm-format --validate src/ tests/` passes, and
    `API_BASE_URL=http://localhost:4173/api ./build.sh` produces
    `dist/admin/admin.js`.
16. `npm run screenshots` produces `desktop-admin.png` and `mobile-admin.png`
    with no page errors in `manifest.json`.
17. No diff in `atwood_monitor/storage.py`. All CI Python checks (pytest,
    black, isort, flake8, mypy) pass.

## Test plan

- `tests/test_admin_lambdas.py`: extend `test_admin_stats_counts` and add
  tests for criteria 5–11. Use moto to create the posts, users and web push
  tables, an SNS topic with a confirmed email, a pending email and a Lambda
  subscription, and CloudWatch `put_metric_data` with explicit timestamps.
  Call `build_stats` with a fixed `now`. Set the `POSTS_TABLE`,
  `NOTIFY_TOPIC_ARN` and `ENVIRONMENT` env vars before `reload_module`.
  Moto auto-confirms email subscriptions, so build the pending case by
  monkeypatching `list_subscriptions_by_topic`.
- `tests/test_lambdas.py`: add tests for `notify_subscribers` and
  `dynamo.record_notification` (criteria 1–4).
- `elm-frontend/tests/AdminStatsTests.elm`: criteria 12–14. Embed the fixture
  JSON as a string literal.
- Manual/CI: the screenshot workflow posts admin before/after images.

## Open questions

## UX/UI

Matches the existing `Main.elm` look: page background `rgb(245,248,255)`, white
cards with `rounded-xl` and the same soft shadow, slate text (slate-800 headings,
slate-500 secondary, ~14px), blue-600 primary buttons, red-700 errors,
green-700 success. Use `elm-ui` for layout and `Html.Styled` + `Tw.*` for
buttons and inputs, as `Main.elm` does. The page is a single column, max width
~1024px, centred, `p-4` on mobile and `p-8` on desktop.

### Flow
`/admin/index.html` -> Login card -> Dashboard. "Log out" returns to the login
card and clears the secret. The secret is in the model only. Because it is never
persisted, a page reload logs the admin out. That is intended.

### Layout
Dashboard order (top to bottom):
1. Header row: `<h1>` "Admin" (left), "Last notification: <date>" as muted text,
   then "Refresh" (secondary button) and "Log out" (text button) on the right.
   On mobile the title is on its own row and the buttons wrap below it,
   each at least 44px tall.
2. Stat cards in a grid: 2 columns below 640px, 4 columns from 640px up.
   Order: Email confirmed, Email pending, Web push, Posts announced (12 mo),
   Emails sent (12 mo), Push delivered (12 mo), Push failure rate (12 mo).
   The last card spans the remaining space. Each card has a small slate-500
   label above a large (28px, bold, slate-800) number. Use `tabular-nums`.
3. Subscriber mix card: a single horizontal stacked bar (not a donut: it is
   simpler to label and to read on mobile). Below it is a legend with colour
   swatch, label, count and percent. Legend sits in a column on mobile and a
   row on desktop.
4. "Last 12 months" card: grouped bar chart. One pair of bars per month
   (emails sent, push delivered), with a month label on the x-axis ("Dec",
   "Jan", ... plus the two-digit year on January and the first month), and
   three horizontal grid lines with value labels (0, mid, max).
   SVG uses `viewBox="0 0 640 240"`, `width="100%"`, `height="auto"` and
   `preserveAspectRatio="xMidYMid meet"`, so it scales down. On screens narrower than 480px,
   wrap the SVG in a container with `overflow-x: auto` and `min-width: 480px`
   so that labels stay legible and the page itself never scrolls sideways.
   Legend above the chart: swatch and "Emails sent", swatch and "Push delivered".
5. "Delete subscriber" card (existing feature) at the bottom, visually separated
   with a red-700 heading accent only on the button.

### Chart colours (all on white; non-text graphics need >= 3:1)
| Use | Colour | Hex |
|-----|--------|-----|
| Emails sent, email confirmed | blue-600 | `#2563eb` (5.2:1) |
| Push delivered, web push | emerald-700 | `#047857` (5.5:1) |
| Email pending | amber-600 with a 1px slate-800 outline | `#d97706` |
| Failure | red-700 | `#b91c1c` |
| Grid lines / axis | slate-200 / slate-500 | `#e2e8f0` / `#64748b` |

Blue and emerald differ in lightness as well as hue. Never rely on colour
alone: every bar segment and series is also named in the legend and in the
`<title>`/table fallback below. Value labels use slate-800 or slate-600 text, at
least 12px (SVG text, not scaled below 12px on mobile because of the
min-width rule above).

### States
| State | What the user sees |
|-------|--------------------|
| Logged out | Login card: heading "Admin login", label "Admin secret" (`<label for>`, `type=password`, `autocomplete="current-password"`), button "Log in". Button is disabled when the field is empty. |
| Logging in / loading | Button text "Logging in..." and disabled. Inputs stay. On the dashboard after login or Refresh: show the previous data dimmed to 60% opacity with `aria-busy="true"`; on first load show 7 grey skeleton cards (`animate-pulse`, `bg-slate-200`) and a 240px grey chart block. The Refresh button reads "Refreshing..." and is disabled. |
| Error (login) | Under the field, `role="alert"` text in red-700: "Login failed or API unreachable". The field keeps its value and focus returns to it. |
| Error (refresh after login) | Keep the stale data visible. Above the cards, a red-50 banner with red-800 text and `role="alert"`: "Login failed or API unreachable" and a "Try again" button. Do not log out automatically. |
| Partial null | A `null` number shows "—" (em dash) with `aria-label="not available"` on the number, plus a slate-500 note under the card: "Unavailable right now". Email-derived cards (confirmed, pending) go together, and so do push-derived cards (delivered, failure rate). The subscriber mix draws only the known segments and shows the notice "Email counts unavailable" if the email fields are null. The monthly chart draws only the series that has data, and shows "Push data unavailable" under the legend if push is null. Never render NaN or 0 in place of null. |
| Empty / zero | All numbers show 0. Failure rate shows "—" (no sends, not 0%). Subscriber mix with a total of 0 shows an empty slate-200 bar and the text "No subscribers yet". If all 12 months are 0, draw the axes and grid at a 0..4 scale and show the centred text "No notifications sent in the last 12 months". Last notification shows "Never". |
| Success | Dashboard as above. Last notification is formatted like the main page, e.g. "10 Nov 2026, 18:07 UTC". Delete result shows below the delete form in a status area (`role="status"`): green-700 "Deleted <id>" on success or red-700 "Delete failed: <message>" on error, then stats refresh. |
| Permission denied (push) | Not applicable: the admin page never requests notification permission. |

Delete form: label "Email or subscription ID", button "Delete" (red-600, white
text). Ask "Delete <id>? This cannot be undone." with "Delete" and "Cancel"
buttons inline before sending, so a mistyped ID is not removed by one click.
Disable the Delete button when the input is empty.

### Responsive summary
- Under 640px: 2-column cards, stacked header, chart scrolls inside its own
  container if narrower than 480px, inputs and buttons full width.
- 640px and up: 4-column cards, header on one row, delete input and button
  on one row (`flex-row gap-2`).
- No horizontal scroll on `body` at 360px. Check `mobile-admin.png`.

### Accessibility
- Use `<main>`, one `<h1>`, and `<h2>` for each card. Stat cards are a `<dl>`
  (label in `<dt>`, value in `<dd>`).
- Each chart `<svg>` has `role="img"` and an `aria-label` that states the
  data, e.g. "Subscribers: 10 confirmed email, 2 pending email, 4 web push."
  and "Monthly notifications, December 2025 to November 2026. Emails sent: 0,
  ... Push delivered: 0, ...". Also add a visually hidden `<table>` with the
  12 months and both series, with `sr-only`, so screen readers get exact values.
- Form fields have visible `<label>`s, not placeholders alone. Enter submits
  the login form (use a real `<form>` with `onSubmit`).
- Focus: after login success move focus to the `<h1>` (`tabindex="-1"`). After
  a login error move focus to the secret field. After Log out focus the secret
  field. Use the existing focus ring `outline 2px solid #2563eb` with offset
  from `Main.elm` on all buttons and inputs. Tab order follows the visual order
  above. The confirm step in delete moves focus to its "Cancel" button.
- Contrast: body text slate-800/slate-500 on white (>= 4.5:1; do not use
  slate-400 for text). Error text red-700 on white or red-50 (>= 4.5:1).
- Announce loading and results to assistive tech with `aria-busy` and the
  `role="alert"` / `role="status"` regions above. Respect
  `prefers-reduced-motion` by turning off `animate-pulse`.
- Add `<meta name="robots" content="noindex">` to `admin/index.html` and the
  `<title>` "Admin - Atwood Alerter".

### Screenshot fixture
`fixtures/admin.json`: 12 months with a mix of 0 and non-zero values (peak month
about 5x the smallest non-zero month), `email_pending` > 0, and
`notifications.push_failure` set to `null` with the `push_*` monthly fields left
as numbers. This exercises the partial-null card note.
