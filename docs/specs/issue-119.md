# Spec: Recent releases list with sell-out times (#119)

## Problem

The main page only shows the latest release. Visitors can't see how fast
Atwood releases sell out, and that speed is the main reason to turn on alerts.
Today `sold` is computed once, when the scraper first sees a post, and the
Posts item is never updated after that, so we have no record of when a release
sold out. We need the scraper to record a `sold_at` time, `/status` to return
the recent releases, and a "Recent releases" section on the main page.

## Scope

In scope:
- `lambda/lambda_function.py`: re-check recent unsold posts and record `sold_at`.
- `lambda/dynamo.py`: helpers to batch-read posts and mark one sold.
- `lambda/status_lambda.py`: add `recent_releases` to the `/status` response.
- `elm-frontend/src/RecentReleases.elm` (new, no ports), `src/DateHelper.elm`,
  `src/Main.elm`: decode and render the section.
- `elm-frontend/screenshots/fixtures/status.json` and `screenshots/capture.mjs`.
- Tests in `tests/test_lambdas.py`, `elm-frontend/tests/`.

Out of scope:
- `atwood_monitor/storage.py`, the Posts key schema, any GSI, and any table,
  construct or resource name. **No CDK or API Gateway change at all.**
- A new endpoint. We extend `GET /status` instead (see Design).
- Backfilling `sold_at` for existing posts. They show "Sold out" with no duration.
- Fixing the existing gap where only `posts[0]` of each feed is saved. Posts
  that aren't in the table are never re-checked or listed.
- Showing the sell-out duration on the latest-release card, and adding
  `sold_at` to `__meta__.last_seen_post`.
- New Python or Elm dependencies. Nothing goes in `layer/requirements.txt`.

## Design

### 1. Sold-out detection and re-checks (`lambda/lambda_function.py`)

Detection today: `is_sold(text)` looks for `SOLD_PATTERNS` in the last two
lines of the post's `div.post-body` text. Keep it unchanged. Extract the
fetch-and-parse code that appears twice in `lambda_handler` into
`fetch_sold_status(url: str) -> bool`, which calls
`requests.get(url, timeout=REQUEST_TIMEOUT_S)` (10 s) and returns `is_sold(...)`.
Use it for the newest post, for seeding and for re-checks.

Constants:
- `RECHECK_WINDOW = timedelta(days=7)`
- `MAX_RECHECKS_PER_RUN = 3` (extra blog GETs per run, on top of the newest post
  that is already fetched every minute)

New function `recheck_recent_posts(entries, newest_id, newest_sold, now)`.
It runs after the seed branch returns (never on the seeding run) and after the
new-post branch:
1. Candidates are the feed entries already in memory (`feed.entries`, no extra
   request) whose `published` parses with `email.utils.parsedate_to_datetime`
   and is within `RECHECK_WINDOW` of `now`. Skip entries with no `id` or an
   unparseable date. Order them newest first.
2. Read the candidates' items with one `batch_get_item` (new
   `dynamo.get_posts(post_ids) -> dict[str, dict]`, which handles
   `UnprocessedKeys`). Keep only items that exist and have `sold` false.
   Entries that aren't in the table are ignored and never created.
3. For the newest entry, reuse `newest_sold` (it was fetched this run) and don't
   make another request. For the others, call `fetch_sold_status` for at most
   `MAX_RECHECKS_PER_RUN` of them, newest first. If a fetch raises, log it and
   go on to the next one. A failed fetch still counts towards the cap.
4. When a post is now sold, call the new `dynamo.mark_sold(post_id, sold_at)`:
   `update_item` with `SET sold = :true, sold_at = :ts` and
   `ConditionExpression="attribute_not_exists(sold_at) AND sold = :false"`.
   Catch `ConditionalCheckFailedException` and ignore it, so `sold_at` is only
   written once.
5. Wrap the whole function in `try/except Exception` and log failures, so a
   re-check failure never stops `save_metadata` from running.

`sold_at` is the detection time, `now`, in ISO 8601 UTC with seconds precision
and a `Z` suffix: `now.strftime("%Y-%m-%dT%H:%M:%SZ")`. A post that is new and
already sold the first time we see it gets `sold: true` and **no** `sold_at`,
because we don't know when it sold. Seeded posts get no `sold_at` either.

Worst case per run: 1 GET for the newest post (as today) plus 3 GETs, one
`batch_get_item` and at most 4 `update_item` calls. Releases are days apart,
so the usual number of extra GETs is 0 to 1.

### 2. API: extend `GET /status` (`lambda/status_lambda.py`)

We extend `/status` because it needs no API Gateway, CDK or IAM change: the
status Lambda already has `posts_table.grant_read_data`. The frontend already
polls it every 60 s. Existing keys stay unchanged, so the change is backwards
compatible.

Add `"recent_releases": [...]`, built by `recent_releases(limit=10)`:
- Paginated `scan` of the Posts table with a
  `ProjectionExpression` of `post_id, title, #u, published, image_url, sold, sold_at`.
  `url` is a reserved word, so alias it with `ExpressionAttributeNames`. The
  table holds one item per release plus `__meta__` and the `__stats__#YYYY-MM`
  items, so it is small (tens to low hundreds of items). A scan is cheap and
  needs no key-schema change.
- Drop items whose `post_id` starts with `__`.
- Sort by `published`, newest first. Parse it with `parsedate_to_datetime`, fall
  back to `datetime.fromisoformat` (seeded fallback values are ISO), and sort
  unparseable values last. Take the first `limit`.
- Each element has exactly these keys: `title`, `url`, `published`,
  `image_url` (string or `null`), `sold` (bool), `sold_at` (string or `null`).
  Don't return `post_id`.
- If the scan raises, log it and return `"recent_releases": []`, so the latest
  card still loads.

The list includes the latest release, because the latest card doesn't show a
duration.

### 3. Frontend

**`DateHelper.elm`**: add and expose:
- `parseRfcPosix : String -> Maybe Time.Posix`, which parses
  `"Mon, 10 Nov 2026 18:05:00 +0000"` including the time and the `±HHMM` offset.
- `sellOutDuration : String -> String -> Maybe String`, taking `published`
  (RFC 822) and `soldAt` (ISO 8601, parsed with `Iso8601.toTime`).
  If either value doesn't parse, return `Nothing`. Otherwise take
  `d = max 0 (soldAt - published)` in seconds and apply these rules, all
  rounding down:
  - `d < 3600`: `"N min"`, where `N = max 1 (d // 60)`
  - `d < 86400`: `"N hour"` or `"N hours"`, where `N = d // 3600`
  - otherwise: `"N day"` or `"N days"`, where `N = d // 86400`

**`RecentReleases.elm`** (new, plain module, so it can be unit tested like
`SignupModal`):
- `type alias Release = { title, url, published : String, imageUrl : String, sold : Bool, soldAt : Maybe String }`
- `decoder : Decoder Release`. Decode `image_url` with
  `oneOf [ string, null "" ]`. Decode `sold_at` as optional or null to `Nothing`.
- `listDecoder : Decoder (List Release)`. A missing `recent_releases` field
  decodes to `[]`, so the frontend still works if it deploys before the backend.
- `statusLabel : Release -> String` returns `"Available"` if not sold. If sold,
  it returns `"Sold out in " ++ dur` when `sellOutDuration` succeeds, and
  `"Sold out"` otherwise.

**`Main.elm`**: add `recentReleases : List Release` to `StatusData`. Decode it
with `field "recent_releases" ...` wrapped so that a missing field gives `[]`.
Because `Decode.map6` is full, use `andThen` or `map2`. Render
`viewRecentReleases model.status` below `viewStatus` inside the same centred
640px column, in a card that uses `cardAttrs`:
- A heading styled like "LATEST RELEASE" (13px, slate500, letter-spacing):
  `"RECENT RELEASES"`, with `Region.heading 2`.
- `Loading`: the heading plus `"Loading recent releases..."` in slate500.
- `Failure` or `NotAsked`: render `none`. The latest card already shows the error.
- `Success` with `[]`: the heading plus `"No recent releases yet."`.
- Each row: a 56px rounded thumbnail (omitted when `imageUrl` is empty), the
  title as a `newTabLink` with `aria-label "<title> (opens in new tab)"`, the
  date as `cutOffTralingZeroes published`, and the status pill. The pill uses
  the same colours, radius and font as the latest card's badge, with
  `statusLabel` as its text. Separate rows with a 1px slate-200 top border.
  The layout must stay usable at a 390px width (use `wrappedRow` for the
  date and pill).

The UX/UI agent may refine the visuals in its section of this spec.

### 4. Screenshots

- `fixtures/status.json`: add `recent_releases` with 5 entries. The first is
  the same post as `last_seen_post` (Available). Then one sold after 7 min
  (`sold_at` 7 min after `published`), one after 3 hours, one after 2 days,
  and a legacy sold post with `sold_at: null` and `image_url: null`. Use
  `/icon.png` for images, because external requests are aborted.
- `capture.mjs`: let a scenario override the `/api/status` body. Add the
  scenario `recent-empty`, which serves the fixture with `recent_releases: []`
  and waits for the text "No recent releases yet.". The existing `main`
  scenario shows the populated list.

### Guardrails

No change to `storage.py`, the table key schema, or stack or resource names.
New attributes (`sold_at`) are schemaless additions to existing items. There are
no new dependencies and no infra changes.

## Acceptance criteria

1. `fetch_sold_status(url)` calls `requests.get` with a `timeout` and returns
   `is_sold` of the `post-body` text. The newest-post and seeding paths use it.
2. For an existing post published 2 days ago with `sold: false`, a run whose
   fetched HTML ends with "Sold out" sets `sold: true` and `sold_at` equal to the
   frozen `now` formatted as `YYYY-MM-DDTHH:MM:SSZ`.
3. A post that already has `sold_at` is never fetched again, and a second
   detection doesn't change `sold_at`. `mark_sold` is conditional and swallows
   `ConditionalCheckFailedException`.
4. Posts published more than 7 days ago, posts already sold, and feed entries
   that aren't in the table cause no blog request and no write.
5. With 6 unsold in-window posts in the table and feed (the newest included),
   one run makes at most 1 + 3 `requests.get` calls. The 3 re-checks are the
   next-newest posts.
6. The newest post is re-checked from the result already fetched that run,
   with no second GET for its URL, and gets `sold_at` when it flips to sold.
7. A new post first seen as sold is saved with `sold: true` and no `sold_at`.
   The seeding run writes no `sold_at` and makes no re-checks.
8. If a re-check `requests.get` raises, the run still calls `save_metadata`, and
   the other candidates are still checked.
9. `/status` returns `recent_releases` with at most 10 items, sorted by
   `published` newest first (RFC 822 parsed, not sorted as strings), excluding
   `__meta__` and `__stats__#…` items. Each item has exactly the keys `title`,
   `url`, `published`, `image_url`, `sold` and `sold_at`, with `sold_at: null`
   when it is missing. `last_run_time` and `last_seen_post` are unchanged.
10. `/status` follows scan pagination (moto test with `Limit` forcing several
    pages, or with more than 10 posts), and returns `recent_releases: []` with
    status 200 when the table holds only `__meta__`.
11. `sellOutDuration`: 0 s gives `"1 min"`, 59 s gives `"1 min"`, 7 min gives
    `"7 min"`, 59 min 59 s gives `"59 min"`, 60 min gives `"1 hour"`, 3 h 30 min
    gives `"3 hours"`, 23 h 59 min gives `"23 hours"`, 24 h gives `"1 day"` and
    50 h gives `"2 days"`. `sold_at` before `published` gives `"1 min"`. An
    unparseable input gives `Nothing`. A non-`+0000` offset is applied
    (`... 10:00:00 -0800` equals 18:00Z).
12. `statusLabel` gives `"Available"` when not sold, `"Sold out in 3 hours"`
    when sold with a valid `sold_at`, and `"Sold out"` when sold with a missing
    or unparseable `sold_at`.
13. `RecentReleases.decoder` accepts `image_url: null` and `sold_at: null` or a
    missing `sold_at`. The status decoder accepts a response with no
    `recent_releases` key and gives `[]`.
14. The screenshot run produces `desktop-main`, `mobile-main`,
    `desktop-recent-empty` and `mobile-recent-empty` with no `pageerror`.
    The main shots show "Recent releases" with the five fixture states.
15. `git diff main` touches nothing under `atwood_monitor/`, `layer/` or
    `.github/`. All the CLAUDE.md checks pass, and so do `elm-format --validate`
    and `elm-test`.

## Test plan

- `tests/test_lambdas.py` (use `_scraper_env()` and `@mock_aws`): monkeypatch
  `feedparser.parse`, `requests.get` (count the calls per URL) and the clock
  (inject `now` into `recheck_recent_posts`, or patch a module-level
  `_utcnow()`). Cover criteria 1 to 8.
- `tests/test_lambdas.py`: extend the status tests for criteria 9 and 10. Seed
  posts with RFC 822 dates that sort differently as strings, plus
  `__meta__` and `__stats__#2026-11` items.
- `elm-frontend/tests/DateHelperTests.elm`: criterion 11, plus
  `parseRfcPosix` cases.
- `elm-frontend/tests/RecentReleasesTests.elm` (new): criteria 12 and 13.
- Screenshots: update the fixture and `capture.mjs` (criterion 14). The
  `visual-preview.yml` before/after images cover the visual review.

## Open questions

1. Should a release that is already sold the first time the scraper sees it
   get `sold_at = now`? That would show an upper bound such as
   "Sold out in 2 min". This spec leaves `sold_at` unset, so it shows plain
   "Sold out", because we can't tell when it actually sold.
2. Should "Recent releases" leave out the release already shown in the
   latest-release card? This spec includes it, because the card doesn't show
   the sell-out duration.


## UX/UI

### Styling setup

Same as #111: the page is elm-ui. Reuse `cardAttrs`, `slate800`, `slate500`,
`blue600`, `green700`/`red700` and the existing badge colours. No Tailwind
classes, no new dependencies. Extract the existing badge into a shared helper
`statusBadge : Bool -> String -> Element msg` (sold flag, label) in `Main.elm`
and use it in both the latest card and the list, so the two can't drift. The
latest card keeps its text `Available` / `Sold Out` (unchanged, no duration).

### User flow

Read-only section. The user scrolls past the latest card and sees up to 10
releases, newest first, each with its sell-out speed. Rows are not buttons. The
only interactive element per row is the title link (new tab). It refreshes
silently with the 60 s `Tick` (no loading flash: while a refresh is in flight the
old data stays, as the existing status handling does; check this in review).

### Layout

Section is a second card below `viewStatus`: `column (cardAttrs ++ [ spacing 0 ])`
in the same 640px column, so the 24px page spacing applies. Do not nest it in the
latest card.

- Heading: `RECENT RELEASES` styled as the "LATEST RELEASE" eyebrow (13, slate500,
  letter-spacing 1), `Region.heading 2`, with 8px space below. The page title is
  h1, the modal title is h2 but only exists while open, so no conflict.
  elm-ui has no `<ul>`, so add `htmlAttribute (Attr.attribute "role" "list")` on the rows column and
  `role="listitem"` on each row, so screen readers announce "list, 5 items".
- Row: `row [ width fill, spacing 12, paddingXY 0 12 ]`, with
  `Border.widthEach { top = 1, others = 0 }` in slate-200 (`226 232 240`) on every
  row except the first (no divider directly under the heading).
  - Thumbnail: 56x56, `alignTop`, `Border.rounded 8`, `clip`, `image` with
    `description = ""` (decorative; the title link is adjacent, same decision as
    #111). Use the same URL as the latest card; no extra size params.
  - Text column: `column [ width fill, spacing 6 ]`:
    1. Title: `paragraph` containing `newTabLink` (blue-600, underline, medium,
       size 16), so long titles wrap. `aria-label` = `<title> (opens in new tab)`.
       Add a visible focus ring as in #111 (2px blue-600 outline, offset 2).
    2. `wrappedRow [ spacing 12 ]` with the badge (`alignLeft`, auto width) and
       the date (size 14, slate500, `cutOffTralingZeroes published`). Badge first
       so the key info is scanned first; on 390px the date wraps under the badge
       if there isn't room.
- Missing image (`imageUrl == ""`): do not omit the thumbnail slot. Render a 56x56
  placeholder: `el [ width (px 56), height (px 56), Border.rounded 8, Background.color (rgb255 241 245 249) ]`
  (slate-100), no text, `aria-hidden`. Keeping the slot keeps titles aligned down
  the list, which matters in a table-like list. This differs from the latest card
  (#111: omit image so text fills the row) and from the Design section above
  ("omitted when `imageUrl` is empty"). **Conflict, resolved here in favour of
  the placeholder** because rows are compared vertically. If the coder prefers the
  spec's wording, it is non-blocking.
- Image load error (broken URL): the same slate-100 background sits behind the
  `image`, so a failed load shows the placeholder, not a broken icon. Set it on
  the thumbnail wrapper `el`.

### Status pill (matches the latest card)

Same colours, `paddingXY 10 4`, `Border.rounded 999`, `Font.size 14`,
`Font.semiBold` as #111. Colour is never the only signal: the text differs.

| Release | Text | Colours |
|---------|------|---------|
| not sold | `Available` | bg `209 250 229`, text `4 120 87` |
| sold, valid `sold_at` | `Sold out in 7 min` / `Sold out in 3 hours` / `Sold out in 1 hour` / `Sold out in 2 days` | bg `254 226 226`, text `153 27 27` |
| sold, no/invalid `sold_at` | `Sold out` | same |

Note the capitalisation conflict: the latest card says `Sold Out` (capital O,
existing) and the list says `Sold out in ...` (the spec's copy). Keep the spec
copy for the list. Normalising the latest card to `Sold out` is a one-word change
and recommended, but is out of scope unless the coder touches that line anyway;
non-blocking. Contrast: emerald-700 on `209 250 229` and red-800 on
`254 226 226` are both above 4.5:1.

### States

| State | Render |
|-------|--------|
| `NotAsked` | `none` |
| `Loading` | Card shell, heading, `Loading recent releases...` (14, slate500). Min height 96 to limit layout jump. Shown below the latest card's own loading card, so on first load the page shows two short loading cards; acceptable. |
| `Failure` | `none`. The latest card already shows `Could not load the latest release.` and the retry note; a second error would be noise. |
| `Success`, `[]` | Card shell, heading, `No recent releases yet.` (14, slate500). Covers a backend that has not shipped `recent_releases`. |
| `Success`, 1 to 10 | List as above. Never show more than 10 (backend caps it; the view does not need to slice). |
| Permission denied | Not applicable, this section has no push or signup interaction. |

No retry button, no pagination, no "show more" (out of scope).

### Copy

- Heading: `RECENT RELEASES`, typed in capitals like the existing `LATEST RELEASE` eyebrow.
- Loading: `Loading recent releases...`
- Empty: `No recent releases yet.`
- Link label: `<title> (opens in new tab)`
- Status: `Available`, `Sold out`, `Sold out in <N> min|hour|hours|day|days`.

### Responsive

- 390px: card is `fill` inside 20px page padding; the 56px thumbnail stays; title
  wraps over multiple lines; the badge and date wrap onto two lines when needed.
  No horizontal overflow: the text column must be `width fill` and long unbroken
  titles must wrap (the `paragraph` handles spaces; very long URLs-as-titles are
  not expected). Reviewer will check the mobile screenshot for overflow.
- 1280px: same 640px centred column; no multi-column layout; the badge and date
  fit on one line.
- No breakpoint code.

### Accessibility

- Heading level 2 under the h1 page title. Rows have `role=list/listitem`.
- Title is a real link (`<a>` via `newTabLink`) with an `aria-label` that adds
  `(opens in new tab)`. The visible text is contained in the label, so voice
  control still works.
- Thumbnails are decorative (`alt=""`) because the title is adjacent; the
  placeholder is `aria-hidden`.
- Status is conveyed by text in the pill, not colour alone. The date is plain
  text. Date text uses slate500 (4.8:1 on white), not slate-400.
- Tab order: the "Get alerts" button, the latest-card title link, then the recent
  release links top to bottom. No other tab stops are added.
- Don't use `Region.announce` here: the 60 s refresh would repeat the list to
  screen readers.
- Link focus rings must be visible (2px blue-600, offset 2), as in #111.

### Screenshot scenarios (`capture.mjs`)

- `main` (desktop 1280 and mobile 390): populated list. Review checks that all
  five fixture rows are visible: `Available`, `Sold out in 7 min`,
  `Sold out in 3 hours`, `Sold out in 2 days`, and the legacy `Sold out` with a
  placeholder thumbnail (fixture `image_url: null`). Mobile: no horizontal
  overflow, the badge and date wrap cleanly.
- `recent-empty`: the heading plus `No recent releases yet.`, wait for that text.
- Optional, non-blocking: `recent-failure` serves a 200 `/status` that works but
  the Failure state of the whole status request is already covered by the latest
  card, so this section is simply absent. Skip it unless cheap.
- The fixture must include one long title (about 90 characters) in a row, to prove
  wrapping on mobile. Make it the 3-hour entry.
- The signup dialog scenario (`signup-dialog`) is unaffected, but the page
  behind the dialog now has a longer body. Check that the backdrop covers the
  whole viewport at 390px with the taller page.

### Conflicts and notes for the coder

1. Missing image: placeholder here vs "omitted" in Design section 3
   (see Layout). Placeholder wins.
2. `Sold Out` (latest card) vs `Sold out in ...` (list): see the pill section.
3. Design says the pill uses "the same ... as the latest card's badge": do it by
   sharing one helper, not by copying.
4. A 56px thumbnail is smaller than the 80px latest card image on purpose, so the
   latest release stays the visual focus.
