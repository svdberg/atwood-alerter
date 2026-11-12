# Spec: Improve the UX of the main window (#111)

## Problem

The landing page (`elm-frontend/src/Main.elm`) shows a "latest Atwood release"
card whose layout looks unfinished. The page title ("Atwood Sniper!") is
full-width and left-aligned. The card is capped at 600px but sits flush left.
The image/text row and the "Available"/"Sold Out" badge don't line up cleanly.
Below the card, a full-width "Subscribe to Alerts" box (email field, subscribe
button, push-notification button) is always visible and pulls attention from
the release info. Users need the release status to be the clear focus of the
page, with email and push signup still easy to reach through a modern modal
dialog.

## Scope

In scope (frontend only, `elm-frontend/`):
- Re-layout the status card and page header: centred, consistent width, aligned
  content.
- Replace the inline subscribe box with a "Get alerts" call-to-action button
  that opens an accessible modal dialog. The dialog holds the existing email
  form, its status messages and the existing push-notification section.
- Extract the dialog state logic into a new port-free module so it can be unit
  tested.

Out of scope:
- Any backend, API, Lambda, CDK or DynamoDB change. `POST {apiBaseUrl}/subscribe`
  with body `{"email": ...}` and `GET {apiBaseUrl}/status` keep their current
  shape.
- Changes to the ports (`requestPushRegistration`, `pushRegistrationResponse`,
  `subscribeToPush`) or to the JS in `public/index.html`.
- The admin frontend (`elm-frontend/admin/`), `public/sw.js`, the manifest.
- New client-side email validation, dark mode, or new Elm/npm dependencies.
  `elm/browser` already provides `Browser.Events` and `Browser.Dom`.

## Design

**Files:**
- `elm-frontend/src/Main.elm`: view, model and update changes.
- `elm-frontend/src/SignupModal.elm` (new, plain `module`, no ports): dialog state
  and pure transitions.
- `elm-frontend/tests/SignupModalTests.elm` (new).

**Model:** add `signupOpen : Bool` to `Model`. Initial value is `False`. Keep
`email`, `statusMsg` and `pushStatus` as they are. Move the `StatusMsg` type
into `SignupModal` and import it into `Main`. `SignupModal` exposes pure
helpers on a record such as
`{ open : Bool, email : String, statusMsg : StatusMsg }`:
- `openModal`: sets `open = True`.
- `closeModal`: sets `open = False`. Resets `statusMsg` to `Idle` unless it is
  `Sending`. Keeps `email` unless the last result was `Sent`, in which case it
  clears it.
- `onSubscribeResult : Bool -> ...`: on success sets
  `Sent "Check your email to confirm!"` and clears `email`. On failure sets
  `Error "Failed to subscribe."`. These are the same strings as today.
- `escapeDecoder : msg -> Decoder msg`: succeeds only when `key == "Escape"`.

**New `Msg` variants:** `OpenSignup`, `CloseSignup` and `NoOp` (for the
`Browser.Dom.focus` result). Opening returns
`Task.attempt (\_ -> NoOp) (Browser.Dom.focus "signup-email")`. `Submit` and
`GotSubscriptionResult` keep the same HTTP request (same URL, body and
`expectString`). Only the model bookkeeping moves to `SignupModal`.

**Subscriptions:** `Sub.batch` the existing `pushRegistrationResponse` with
`Browser.Events.onKeyDown (SignupModal.escapeDecoder CloseSignup)`. Add the
Escape listener only when `signupOpen` is `True`.

**Layout (elm-ui):**
- Wrap the content in a single `column [ centerX, width (fill |> maximum 640), spacing 24, padding 20 ]`
  on the existing light background. The header row has the title on the left
  and the "Get alerts" primary button on the right (`alignRight`). On narrow
  viewports it may wrap; use `wrappedRow`.
- Status card: drop the duplicated inner "Atwood Blog Monitor" heading or demote
  it to a small subtitle. Use the order latest post, then badge, then meta.
  The post row is `row [ spacing 16, width fill ]`. The 64px image becomes
  80px with `alignTop`. The text column is `width fill`. The title is a
  `paragraph` so long titles wrap. The badge is `el [ alignLeft ]` so it
  doesn't stretch. "Last checked" and "Days since last tool release" sit in a
  footer row with muted text, separated from the post by spacing.
- Loading and Failure states render inside the same centred card container, so
  the page doesn't jump.

**Modal:** render via `inFront` on the root element when `signupOpen` is
`True`.
- Backdrop: full-size `el` with `Background.color (rgba255 15 23 42 0.5)`. A
  click on the backdrop sends `CloseSignup`.
- Dialog panel: `centerX, centerY, width (fill |> maximum 420)`, white,
  rounded, with a shadow. Clicks inside the panel must not bubble to the
  backdrop. Make the panel a sibling layered via `inFront` of the backdrop,
  not a child.
- Attributes: `htmlAttribute` with `role="dialog"`, `aria-modal="true"` and
  `aria-labelledby="signup-title"`.
- Contents: a heading with `id="signup-title"` ("Get notified of new
  releases"), a close button with `aria-label="Close"` that sends
  `CloseSignup`, the email input with `id "signup-email"` and a visible label,
  `styledButton "Subscribe" Submit`, `viewStatusMsg`, a divider, and the
  existing `viewPushSection`.

**Guardrails:** none of the CLAUDE.md guardrails apply. There are no
`storage.py`, stack/resource, credential, `ci-cd.yml` or `layer/` changes.

## Acceptance criteria

1. `SignupModal.openModal` on a closed state returns a state with `open == True`
   and `email` and `statusMsg` unchanged.
2. `SignupModal.closeModal` returns `open == False`. It resets `statusMsg` from
   `Error _` or `Sent _` to `Idle`, and leaves `Sending` unchanged.
3. `closeModal` after a `Sent` result clears `email`. After an `Error` result
   it keeps `email`.
4. `onSubscribeResult True` yields `Sent "Check your email to confirm!"` and an
   empty `email`. `onSubscribeResult False` yields `Error "Failed to subscribe."`
   and keeps `email`.
5. `Json.Decode.decodeString (escapeDecoder ()) "{\"key\":\"Escape\"}"` succeeds.
   The same call with `"Enter"` fails.
6. `Main.init` produces a model with `signupOpen == False`, so the email form is
   not rendered on page load. The main page shows a "Get alerts" button
   instead of the inline subscribe box.
7. The subscribe request is unchanged: `POST apiBaseUrl ++ "/subscribe"` with JSON
   body `{"email": <model.email>}`. Verify by code review/diff, because Elm
   tests can't inspect `Cmd`.
8. The push-notification UI (`viewPushSection`) appears only inside the
   modal. The port names and signatures are unchanged.
9. `cd elm-frontend && npx elm-format --validate src/` exits 0.
10. `elm make src/Main.elm --output=/dev/null` succeeds. `elm-test` passes,
    including the existing `DateHelperTests` and the new `SignupModalTests`.

## Test plan

- Add `elm-frontend/tests/SignupModalTests.elm` covering AC 1–5 with
  `elm-explorations/test` (already in `test-dependencies`). Import only
  `SignupModal`, not the `port module Main`.
- Leave `tests/DateHelperTests.elm` untouched. It must still pass.
- No pytest changes; the Python suite should still pass unchanged.
- Manual or UX review: check the layout at about 375px and about 1280px
  widths. Check that Escape, the backdrop and the close button dismiss the
  dialog, that the email field takes focus on open, and that the success and
  error messages show inside the dialog.

## Open questions


## UX/UI

### Styling setup (what to use)

The page is laid out with **elm-ui** (`Element.*`), not Tailwind classes.
Tailwind enters only through `elm-tailwind-modules` (`Tw.*`, `Twt.*`) inside
`styledButton`, which renders a real `<button>` via `Html.Styled`. So "Tailwind
classes" below means the `Tw.*` utilities in `styledButton`, and elm-ui
attributes with the Tailwind palette RGB values already used in `Main.elm`
(slate-800 `30 41 59`, slate-500 `100 116 139`, blue-600 `37 99 235`). Don't
add new dependencies or a second styling approach.

### User flow

1. Page loads: header (title left, "Get alerts" button right), then the status
   card. No form is shown.
2. User clicks "Get alerts". The modal opens and the email field has focus.
3. User enters email and presses "Subscribe" (or Enter in the field). Result
   shows inside the modal. Optionally they use "Enable Push Notifications"
   below the divider.
4. User closes with the close button, Escape or a backdrop click. Focus returns
   to the "Get alerts" button (give it `htmlAttribute (Attr.id "get-alerts")`
   and run `Browser.Dom.focus "get-alerts"` from `CloseSignup`, ignoring the
   result with `NoOp`).

### Page layout

- Root `column`: `[ width fill, height (minimum 0 fill), Background.color (rgb255 245 248 255) ]`
  with the modal attached via `inFront`. Inner column per spec
  (`centerX`, `width (fill |> maximum 640)`, `spacing 24`, `padding 20`).
  Remove `Element.clip` on the root, it can cut off the dialog and focus ring.
- Header: `wrappedRow [ width fill, spacing 12 ]`; title `el [ Font.size 28, Font.bold, Font.color slate-800, alignLeft ]`
  using `Region.heading 1`; "Get alerts" `alignRight`, auto width (not
  `w_full`). Drop the "Sniper!" emoji clutter; keep the title text unchanged.
- "Get alerts" button: a real button (`Input.button` or `styledButton`
  variant) with `Tw.bg_color Twt.blue_600`, `Tw.text_color Twt.white`,
  `Tw.px_4`, `Tw.py_2`, `Tw.rounded`, `Tw.font_medium`, plus visible focus
  (`Tw.focus_ring`-style via `Css.focus` or elm-ui `Element.focused` with a
  2px blue-600 outline offset). Label: `Get alerts` (emoji optional, must be
  `aria-hidden`; prefer none).
- Status card (all states use the same container: white, `Border.rounded 12`,
  existing shadow, `padding 24`, `width fill`, `spacing 20`):
  1. Small uppercase eyebrow "Latest release" (size 13, slate-500, letter
     spacing 1) replaces the "Atwood Blog Monitor" heading and "Latest post:"
     line.
  2. Post row `row [ spacing 16, width fill ]`: 80x80 image (`alignTop`,
     `Border.rounded 8`, `clip`); text column `width fill, spacing 8` with the
     title as `paragraph` containing the `newTabLink` (blue-600, underline,
     medium, size 18), the badge below (`alignLeft`), then the post date (size
     14, slate-500).
  3. Footer: `Border.widthEach { top = 1, others = 0 }` in slate-200
     (`226 232 240`), `paddingEach { top = 16, ... }`, `wrappedRow [ spacing 24 ]`
     of two muted items (size 14, slate-500): `Last checked: <time>` and
     `Days since last tool release: <n>`. Drop the emoji prefixes or mark them
     decorative.
- Badge: keep colours (Available: bg `209 250 229`, text `4 120 87`; Sold Out:
  bg `254 226 226`, text `153 27 27`); `paddingXY 10 4`, `Border.rounded 999`,
  `Font.size 14`, `Font.semiBold`. Text label is the information, never colour
  alone.

### Status card states

| State | Render |
|-------|--------|
| `NotAsked` | Same card shell with no body (or nothing; unreachable at runtime). |
| `Loading` | Card shell, body `Loading latest release...` (slate-500). Wrap in `Region.announce`-free plain text; no spinner needed. Min height ~140px to limit layout jump. |
| `Failure` | Card shell with `Could not load the latest release.` (red `185 28 28`) and a muted line `We'll retry automatically in a minute.` (the 60s `Tick` already retries). No new retry button needed. |
| `Success` | Layout above. If `lastPostImageUrl` is empty, omit the image so text fills the row. |
| Empty | There is no empty variant in the data model (status always has a post). Don't add one. |

Image `description`: use the post title, not "Latest blog post image" (or `""`
if treated as decorative next to the title link). Prefer `""` since the title
is adjacent.

### Modal

Structure (backdrop and panel are siblings, both under the root `inFront`):

```
el [ width fill, height fill, inFront panelWrapper
   , Background.color (rgba255 15 23 42 0.5), Events.onClick CloseSignup ] none
```

- Panel wrapper: `el [ centerX, centerY, width (fill |> maximum 420), paddingXY 16 0 ]`
  so there is a 16px gutter on 375px screens.
- Panel: white, `Border.rounded 12`, `padding 24`, `spacing 16`,
  `Border.shadow { offset = (0, 10), blur = 30, size = 0, color = rgba255 0 0 0 0.25 }`,
  `htmlAttribute` `role="dialog"`, `aria-modal="true"`,
  `aria-labelledby="signup-title"`. On mobile cap height:
  `height (shrink |> maximum 640)` with `scrollbarY` so the push section stays
  reachable on short screens (landscape phones).
- Header row: heading `Get notified of new releases` (size 20, bold, slate-800,
  `id="signup-title"`) left; close button right: 32x32 hit area minimum (44x44
  preferred on touch), label text `×` with `aria-label="Close"`, slate-500,
  visible focus ring. `type="button"`.
- Intro line (size 14, slate-500): `We'll email you when a new Atwood release is posted.`
- Email field: `Input.email` with a **visible** label `Email address`
  (`Input.labelAbove`, size 14, slate-700), `id="signup-email"`, placeholder
  `you@example.com`, `autocomplete="email"` and `inputmode="email"` via
  `htmlAttribute`. Border slate-300 on white is below 3:1 for a form control
  boundary; use slate-400 `148 163 184`... which is also ~2.5:1, so use slate-500
  `100 116 139` (4.8:1) for the input border. Font size 16 (prevents iOS zoom).
- Enter in the field triggers `Submit` (keydown decoder for `Enter` on the
  input, same pattern as `escapeDecoder`); ignored while `Sending`.
- Submit button: full width, `Subscribe`.
- Status message (below the button), with `Region.announce` (aria-live) so
  screen readers read changes.
- Divider: 1px slate-200 line, then `viewPushSection`.

### Modal states

| State | Visible | Copy | Behaviour |
|-------|---------|------|-----------|
| Idle | Empty/typed field, enabled button, no message | button `Subscribe` | Focus on field at open. |
| Sending | Button shows `Subscribing...` and is disabled (`disabled` attr, `Tw.opacity_60`, `cursor-not-allowed`) | status line `Sending...` (slate-600 `71 85 105`) | Escape/backdrop/close still allowed per spec (`closeModal` keeps `Sending`). Prevents double submit. |
| Success | Green message, field cleared | `Check your email to confirm!` | Keep modal open so the user reads it; button returns to `Subscribe`. Colour `4 120 87` (emerald-700, 5.5:1), prefixed by a check glyph `✓ ` (aria-hidden) so meaning is not colour-only. |
| Error | Red message, email kept | `Failed to subscribe.` | Colour `185 28 28` (red-700, 6.5:1) with `! ` prefix. Optionally append ` Please check the address and try again.` if the coder keeps the existing string identical for tests, add it only in the view, not in `SignupModal`. |
| Push idle | Section `Push Notifications` + button | `Enable Push Notifications` | Same blue button style as Subscribe, full width. |
| Push requesting | Muted text | `Requesting permission...` | Button hidden to avoid re-click. |
| Push granted | Section hidden (existing) | Replace with `Push notifications are on.` (green, as above) so users get confirmation inside the modal. Small addition, non-blocking. | |
| Push denied (permission denied) | Red text | `Push permission denied. Allow notifications for this site in your browser settings, then try again.` | Show the idle button again below so users can retry after changing settings. |
| Push failed | Red text | `Push registration failed: <msg>` (unchanged) | Same. |

Empty submit: no new client-side validation (out of scope). `Input.email` plus
server response covers it. Browser-native validation does not apply since there
is no `<form>`; don't add one.

### Responsive behaviour

- 375px: inner column is `fill` with 20px padding; header wraps so the button
  drops below the title if needed; status post row keeps the 80px image with
  title wrapping; footer items stack (`wrappedRow`); modal is full width minus
  16px gutters and scrolls internally if taller than the viewport.
- 1280px: content is centred at 640px; modal is 420px centred. No sidebar.
- Use `Element.classifyDevice`/flags only if needed; prefer `fill |> maximum`
  and `wrappedRow` so no breakpoint code is required.

### Accessibility

- Semantics: title is `h1` (`Region.heading 1`), modal title is `h2`
  (`Region.heading 2`), dialog `role="dialog"`/`aria-modal="true"`/
  `aria-labelledby="signup-title"`; "Get alerts" is a button, not a link;
  the post title is a link and opens in a new tab (add `(opens in new tab)` as
  visually hidden text or an `aria-label` on the link).
- Focus management: on open, focus `signup-email`; on close return focus to
  `get-alerts`. Tab order inside the dialog: close button, email, Subscribe,
  Enable Push Notifications. Put the close button after the heading in DOM
  order. Implement a light focus trap: on `Tab` at the last element wrap to the
  first (and Shift+Tab reverse) through a keydown handler on the panel, or
  at minimum mark the background content `aria-hidden="true"` and `inert` via
  `htmlAttribute` while open. Reviewer will treat a missing trap as
  non-blocking if the background is `aria-hidden`/`inert`, blocking if
  keyboard focus can reach background controls with no mitigation.
- Keyboard: Escape closes (subscription active only while open); Enter submits
  from the email field; Space/Enter activate buttons. No keyboard trap other
  than the intentional dialog focus containment.
- Visible focus: every interactive element needs a visible 2px focus ring
  (blue-600 outline, 2px offset). Don't remove default outlines without
  replacement.
- Contrast (WCAG AA, 4.5:1 text, 3:1 UI): primary buttons use blue-600
  (white on blue-600 = 5.2:1); blue-500 in the current `styledButton` is about
  3.7:1 and fails, so change `Tw.bg_color Twt.blue_500` to `Twt.blue_600`
  (and the push button's `0 122 255` to `37 99 235`). Don't use slate-400 text
  (`148 163 184`, about 2.6:1 on white) for the post date; use slate-500.
  Success green `0 150 0` (about 3.9:1) is replaced by `4 120 87`.
- Screen readers: status messages in `Region.announce`; the badge text reads
  "Available"/"Sold Out"; decorative emoji removed or `aria-hidden`.
- Touch targets: buttons min height 40px (`Tw.py_2` + 16px text is about 40px;
  use `Tw.py_3` for 48px on the modal buttons); close button 44x44.
- Reduced motion: no animation required. If a fade is added, wrap it in
  `prefers-reduced-motion: no-preference`.
