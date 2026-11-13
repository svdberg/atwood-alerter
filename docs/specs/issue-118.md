# Spec: Rich push notifications with release image and high urgency (#118)

## Problem

Web push alerts are generic. The title is `New Blog Post!`, there is no image
and there is no button to open the release. The icon path in
`elm-frontend/public/sw.js` (`icon.jpeg`) also doesn't exist; the file is
`public/icon.png`. Pushes go out with pywebpush's default `ttl=0` and no
urgency, so a push service may drop or delay them. Releases sell out within
minutes, so the alert has to stand out, show the knife, link straight to the
post and arrive right away.

## Scope

In scope:
- `lambda/lambda_function.py`: extend `build_push_payload` (added in #116 / PR
  #120). Do not change the per-protocol SNS format (`default` / `email` /
  `lambda`).
- `lambda/lambda-docker/web_push_lambda.py`: forward `image_url` and send with
  `Urgency: high` and a TTL of 600 seconds.
- `elm-frontend/public/sw.js`: add `image`, `icon` and an "Open release"
  action, open the post on click, and fix the icon path.
- Tests: pytest for both Lambdas, plus a dependency-free Node test for `sw.js`.

Out of scope:
- The email body and subject (#116), the `is_sold` heuristic, and the stats
  recording.
- `atwood_monitor/` (CDK, `storage.py`), the DynamoDB tables, the
  `lambda-docker/Dockerfile`, and `layer/requirements.txt`. No new
  dependencies.
- Elm code (`src/*.elm`), the subscribe flow, and VAPID handling.
- Proxying or caching Blogger images. The notification only references the
  URL.
- `.github/workflows/`: the pipeline's GitHub App can't modify workflows.
  Running the `sw.js` test in CI is a follow-up issue. For now it runs
  locally with `npm run test:sw`.
- `requireInteraction` and `renotify`.

## Design

**1. Scraper payload (`lambda/lambda_function.py`)**

`build_push_payload(post) -> dict` returns:

```python
{"title": "New Atwood release", "body": <body>, "url": post["url"], "image_url": <str|None>}
```

- Reuse `SUBJECT_PREFIX` for the title.
- `body` is `post["title"]`. When `post.get("sold")` is truthy, the body is
  `f"{post['title']} (already sold out)"`.
- `image_url` is `post.get("image_url")` only when it is a string that starts
  with `https://`. Otherwise it is `None`. Blogger serves images over https,
  and this rule stops `http:` and `data:` values from reaching the browser.
  Add a small helper, `_safe_image_url(value) -> str | None`.
- `build_sns_message` and `notify_subscribers` stay as they are. The `default`
  and `lambda` keys carry the new payload automatically.

**2. Web push Lambda (`lambda/lambda-docker/web_push_lambda.py`)**

- Add pure helpers so tests can call them without making network calls:
  - `PUSH_TTL_SECONDS = 600`
  - `build_push_data(msg: dict) -> str`: returns the JSON string sent to the
    browser, with keys `title`, `body`, `url` and `image_url`. It uses today's
    fallbacks (`"Atwood Blog"`, `"New post!"` and the blog root URL).
    `image_url` defaults to `None`, so older messages without the key still
    work.
  - `push_headers() -> dict`: returns a **new** `{"Urgency": "high"}` dict on
    every call. pywebpush's `webpush()` mutates the `headers` dict it is given
    (`headers.update(vapid_headers)`), so the code must not share a
    module-level dict across subscribers.
- `lambda_handler` parses the SNS message once per record, not once per
  subscriber. It then calls
  `webpush(subscription_info=sub, data=build_push_data(msg), vapid_private_key=..., vapid_claims=..., headers=push_headers(), ttl=PUSH_TTL_SECONDS)`.
- pywebpush support: `webpush(..., ttl=0, headers=None, ...)` exists in the
  pinned 1.14.x and in the unpinned version the Dockerfile installs. `ttl` is
  sent as the `TTL` header, and extra headers such as `Urgency` are passed
  through. No dependency change is needed.
- The metrics, the stale-subscription deletion and the `WebPushException`
  handling do not change.

**3. Service worker (`elm-frontend/public/sw.js`)**

- Pull the option-building logic out into a pure function,
  `buildNotification(data)`, which returns `{ title, options }`:
  - `title`: `data.title` or `"New Atwood release"`.
  - `body`: `data.body` or `""`.
  - `SITE_ICON = '/icon.png'`. This fixes the broken `icon.jpeg` path.
  - When `data.image_url` is a string that starts with `https://`, set
    `options.image` and `options.icon` to it. Otherwise set `icon` to
    `SITE_ICON` and leave `image` out of `options`.
  - `badge` is always `SITE_ICON`.
  - `actions: [{ action: 'open', title: 'Open release' }]`.
  - `data: { url: data.url || '/' }`.
  - `tag: data.url` when `data.url` is set; otherwise no `tag` key. Setting a
    tag is a one-liner and harmless: if the same post is pushed twice, the
    second alert replaces the first instead of stacking. `renotify` is not
    set.
- The `push` handler calls `buildNotification` and then `showNotification`.
  If the push data isn't valid JSON, it still shows a notification built from
  `{}`.
- `notificationclick` opens or focuses `event.notification.data.url` both when
  `event.action === 'open'` and when the body is clicked (`event.action` is
  `''`). Browsers that don't support `image` or `actions`, such as macOS
  Safari, ignore those options, so no feature detection is needed.
- Testability: `package.json` has `"type": "module"`, so the test must not
  `require` the file. Instead, load `sw.js` with `node:vm` into a sandbox
  that has a stub `self`, and read `buildNotification` from the context.
  Don't add an export shim or a new npm dependency.
  Add the script `"test:sw": "node --test tests-js/"` to
  `elm-frontend/package.json`. Do **not** edit `.github/workflows/`. Running
  this test in CI is a follow-up.

**Guardrails:** no `storage.py`, stack or resource-name changes, and no new
layer or Docker dependencies. The only new data is one key in the SNS
`lambda`/`default` JSON. The email part of the SNS message is unchanged.

## Acceptance criteria

1. `build_push_payload({"title": "Spring drop", "url": U, "sold": False, "image_url": "https://img/x.jpg"})`
   equals `{"title": "New Atwood release", "body": "Spring drop", "url": U, "image_url": "https://img/x.jpg"}`.
2. With `sold=True`, `body == "Spring drop (already sold out)"`.
3. `image_url` is `None` when the post's `image_url` is missing, `None`, `""`,
   `http://...` or `data:...`.
4. In `notify_subscribers`, `json.loads(message["lambda"])` and
   `json.loads(message["default"])` both equal `build_push_payload(post)`. The
   message keys are still exactly `{"default", "email", "lambda"}`, and the
   `email` body and `Subject` are unchanged from #116.
5. `web_push_lambda.build_push_data({"title": "New Atwood release", "body": "B", "url": U, "image_url": I})`
   parses to the same four keys and values.
6. `build_push_data({})` parses to the old fallbacks with `image_url: None`.
7. For each subscription, `lambda_handler` calls `webpush` with
   `ttl=600` and `headers` that contain `Urgency: high`. Each call gets a
   different dict object (`id` differs between calls).
8. With 2 subscriptions and 1 SNS record, `webpush` is called twice and the
   `data` it receives includes `image_url`. A `WebPushException` with status
   410 still deletes that subscription.
9. `buildNotification({title, body, url, image_url: "https://img/x.jpg"})`
   returns `options.image === options.icon === "https://img/x.jpg"`,
   `badge === "/icon.png"`, `actions[0]` equal to
   `{action: "open", title: "Open release"}`, `data.url === url` and
   `tag === url`.
10. `buildNotification({title, body, url})` (no image) and
    `buildNotification({image_url: "javascript:x"})` have `icon === "/icon.png"`
    and no `image` key.
11. `buildNotification({})` returns the title `"New Atwood release"`,
    `data.url === "/"` and no `tag` key, and does not throw. The options
    never include `requireInteraction`.
12. `sw.js` no longer references `icon.jpeg`.

## Test plan

- `tests/test_lambdas.py`: update
  `test_notify_subscribers_publishes_per_protocol_message` so its expected
  push dict is the new payload (AC 4). Add
  `test_push_payload_fields_and_sold` (AC 1, 2) and a parametrized
  `test_push_payload_rejects_unsafe_image_url` (AC 3).
- New `tests/test_web_push_lambda.py`: put `lambda/lambda-docker` on
  `sys.path`, set `VAPID_PRIVATE_KEY=dummy` and `WEB_PUSH_TABLE`, and import
  under `@mock_aws` with a moto table. Use `monkeypatch` to replace
  `mod.webpush` with a spy, and `mod.cloudwatch.put_metric_data` with a no-op
  if moto rejects it. Cover AC 5 to 8. `pywebpush` is already in the root
  `requirements.txt`.
- New `elm-frontend/tests-js/sw.test.mjs` (`node:test`, `node:vm`,
  `node:fs`). It loads `public/sw.js` into a context with a stub `self`
  (`addEventListener`, `registration`) and `clients`, then covers AC 9 to 12.
  It can also dispatch a fake `notificationclick` with `action: 'open'` and
  assert that `clients.openWindow` was called with the URL.
  Run it with `cd elm-frontend && npm run test:sw`. It runs locally only
  until a follow-up wires it into CI.
- Run the existing pytest suite unchanged otherwise.

## UX/UI

Scope: the only user-facing surface is the OS notification rendered from
`elm-frontend/public/sw.js`. There are no Elm or Tailwind changes, no new
screens and no new dialog states. The signup dialog and the push-permission
flow are untouched.

### User flow

1. A subscriber who already granted push permission receives an alert when a
   new post is scraped.
2. They see the notification (title, body, release image where supported).
3. They click the body or the "Open release" button. The blog post opens in a
   focused existing tab, or in a new window if none is open. The notification
   closes.
4. They can dismiss it without any action. Nothing else happens.

### Copy (exact)

| Element | Text |
|---|---|
| Title | `New Atwood release` |
| Body (available) | `<post title>` |
| Body (sold) | `<post title> (already sold out)` |
| Action button | `Open release` |
| Title fallback (no data) | `New Atwood release` |
| Body fallback (no data) | empty string |

Notes:
- Sentence case, no emoji, no trailing punctuation. The old `New Blog Post!`
  and `📢 New Notification` strings go away.
- The sold suffix is lowercase and in parentheses, appended by the scraper, so
  the service worker never re-derives it.
- "Open release" is the same for sold-out posts. The post is still the best
  place to see what happened, so the label stays constant.
- Keep the body to the post title only. OS notification areas truncate long
  text (roughly 40 to 60 characters per line on mobile, 2 to 3 lines on
  desktop), and the sold-out suffix at the end can be cut off on long titles.
  This is acceptable for v1. Do not move the suffix to the front. If it proves
  a problem, a follow-up could shorten the title.

### States

- Loading: not applicable, the notification is shown as soon as the push
  arrives.
- Success (image present): title, body, small icon (the release image) and the
  large image.
- No image: `image_url` is `None` or not `https://`. Show title, body and the
  site icon `/icon.png`, with no `image` key.
- Empty or malformed payload (invalid JSON, `{}`): still show a notification
  titled `New Atwood release` with an empty body. Clicking it opens `/`.
  Never fail silently, because a missed alert costs the user a release.
- Image fails to load: the browser omits the image and still shows the text.
  No handling is needed in the service worker.
- Permission denied or not yet granted: no notification can be shown, and this
  change does not affect it. The existing subscribe and permission UI in the
  Elm app is unchanged. No new copy is needed.
- Click error (`clients.openWindow` unavailable): the notification is still
  closed. Do not add a fallback UI.

### Graceful degradation

All unsupported options are ignored by browsers, so no feature detection is
needed. The text must therefore carry the whole message on its own.

| Platform | Expected result |
|---|---|
| Chrome / Edge on Windows, Linux, ChromeOS | Title, body, large image and the "Open release" button. |
| Chrome on Android | Title, body, large image and the action button. Collapsed state may show only the small icon and text, and the image appears on expand. |
| Firefox desktop | Title, body and icon. The large image is not shown. Actions are shown on some platforms only. Body click works. |
| Firefox Android | Title, body and icon. No image or actions. Body click works. |
| macOS Chrome / Edge | Text and icon. The image may be dropped by the OS and actions may sit in a hover menu. Body click works. |
| Safari macOS 13+ and iOS/iPadOS 16.4+ (installed web app) | Title and body, with the site icon. No large image, and actions are not supported. Body click works. |

Requirements that follow from this:
- The body click must open the post exactly like the action does. The action
  button is a shortcut, not the only way in.
- The title and body must make sense without the image. Do not put information
  such as price, size or stock only in the image.
- The `icon` must still point at a valid file (`/icon.png`) when there is no
  release image. This fixes the broken `icon.jpeg`.
- Use a single action. Platforms show 0 to 2 actions, and one is the safest.
- `badge` is `/icon.png`. Android renders badges as a monochrome mask, so a
  plain icon may look like a blob. This is acceptable for v1. A dedicated
  monochrome badge asset is a possible follow-up and is out of scope here.

### Responsive behaviour

The notification is drawn by the OS, so there is no Tailwind or layout work.
The image is cropped by the OS to roughly 2:1 to 4:3 depending on platform, so
the subject may be cut at the edges. Nothing in the service worker can control
this, so don't try to resize or proxy the image.

### Accessibility

- Text first: the title and body are short, in plain language, and are what
  screen readers announce (NVDA, VoiceOver, TalkBack read title and body, and
  they list action buttons). The image is decorative and has no alt text in
  the Notifications API, so it must not be the only carrier of meaning.
- The sold-out state is in the body text, not conveyed only by colour or
  imagery.
- The action label `Open release` is a verb phrase that names its result, so
  it is meaningful out of context.
- The click target is the whole notification, so users do not need a precise
  pointer. Keyboard and assistive-tech users get the same result through the
  OS notification controls.
- No `requireInteraction`: notifications dismiss on their own, so they do not
  trap focus or clutter the screen for people using screen magnifiers. Urgency
  comes from the push `Urgency: high` header and the short TTL, not from a
  sticky UI.
- No sound, vibration or `silent` overrides. The OS defaults and user settings
  apply.
- Contrast is controlled by the OS.

### Manual verification (cannot be automated)

After deploy to staging, send a test push and check, on at least Chrome
desktop and one of Safari or Firefox:
1. The title and body match the table above, for both a normal post and a
   sold one.
2. The image appears where supported, and its absence on other platforms
   leaves a clean text-only notification with the site icon.
3. Both the body click and the "Open release" button open the post.
4. A push with no image still shows `/icon.png`.

### Changes to the acceptance criteria

None are required. AC 9 to 12 already cover the copy, action, icon, badge and
fallback behaviour. One clarification: AC 11 fixes the empty-payload body as an
empty string, which the Copy table above matches. Because `sw.js` is the
only frontend file, no Elm screenshots are needed. The `visual-preview.yml`
screenshots will show no difference.
