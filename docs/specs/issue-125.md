# Spec: Store full-size release images instead of 72px Blogger thumbnails (#125)

## Problem

The scraper stores Blogger's 72x72 cropped thumbnail as `image_url`
(e.g. `https://blogger.googleusercontent.com/img/b/…/s72-c/PXL_….jpg`), because
`extract_image_from_entry` in `lambda/lambda_function.py` falls back to the RSS
`media_thumbnail`, which Blogger always serves at `s72-c`. Since #122 that URL is
the large image in push notifications, and the website's release card uses it
too, so both look blurry. Blogger encodes the size in the URL, so rewriting it to
a large size (`s1200`) gives a sharp image everywhere with no extra requests.

## Scope

In scope:
- `lambda/lambda_function.py`: a new pure helper that rewrites Blogger image
  URLs, applied to the value `extract_image_from_entry` returns.
- `tests/test_lambdas.py`: unit tests for the helper and for
  `extract_image_from_entry`.

Out of scope:
- `lambda_handler`, `save_post`/`save_metadata`, `build_push_payload`,
  `_safe_image_url`, email/SNS formatting, and the sold-out logic. #119 is also
  changing the scraper, so keep the diff confined to the image-URL helper area.
- Backfilling posts already stored. The `__meta__` item is rewritten on every
  run, so the latest post updates on its own.
- `atwood_monitor/` (CDK, `storage.py`), DynamoDB tables, `layer/requirements.txt`
  (no new dependencies; use the stdlib `re` / `urllib.parse`), and
  `elm-frontend/`.

## Design

Add, next to `_first_img_src` in `lambda/lambda_function.py`:

```python
BLOGGER_IMAGE_SIZE = "s1200"

def upscale_blogger_image_url(url: str | None) -> str | None: ...
```

Behaviour:
1. `None` (or any non-`str`) and empty strings are returned unchanged.
2. Only Blogger/Google image hosts are rewritten: `blogger.googleusercontent.com`,
   `*.bp.blogspot.com`, and `lh3`–`lh6.googleusercontent.com` (match on the parsed
   hostname, case-insensitive; never a substring of the whole URL). Every other
   URL is returned byte-for-byte unchanged.
3. **Path-segment form**: if the segment immediately before the filename is a
   size token, replace it with `s1200`. Size tokens match
   `^(s\d+|w\d+|h\d+|w\d+-h\d+)(-[a-z0-9]+)*$` (covers `s72-c`, `s1600`,
   `w640-h480`, `w640-h480-p-k-no-nu`, `s320-rw`). Example:
   `…/img/b/R29v/AVvX/s72-c/a.jpg` → `…/img/b/R29v/AVvX/s1200/a.jpg`.
4. **Suffix form**: if the path ends in `=<size token>` (e.g. `=s72-c`,
   `=w640-h480`), replace the suffix with `=s1200`. Example:
   `https://blogger.googleusercontent.com/img/a/AVvX=s72-c` → `…/img/a/AVvX=s1200`.
5. A Blogger URL with no size token is returned unchanged. Scheme, host, query
   string and fragment are preserved. Rewrite at most one token (the one in
   rule 3 or 4), never the filename.

Wiring: apply the helper to whatever `extract_image_from_entry` returns, from
all four sources (`media_content`, `media_thumbnail`, content `<img>`, summary
`<img>`). The least invasive way: wrap each `return <src>` in
`upscale_blogger_image_url(...)`, or move the existing body into
`_find_image_url(entry)` and have `extract_image_from_entry` return
`upscale_blogger_image_url(_find_image_url(entry))`. Both `lambda_handler` call
sites (newest post and first-run seeding) already go through
`extract_image_from_entry`, so the handler itself is not edited.

`_safe_image_url` still runs on the push payload, so a rewritten URL that is
`http://` is still dropped there; nothing changes in that path.

No data-model, API, or infra impact. No CLAUDE.md guardrail is triggered.

## Acceptance criteria

1. `upscale_blogger_image_url(None)` returns `None`, and `upscale_blogger_image_url("")`
   returns `""`.
2. `https://blogger.googleusercontent.com/img/b/R29v/AVvX/s72-c/PXL_1.jpg` becomes
   `https://blogger.googleusercontent.com/img/b/R29v/AVvX/s1200/PXL_1.jpg`.
3. Path segments `s1600` and `w640-h480` (and `w640-h480-p-k-no-nu`) in the same
   position are each rewritten to `s1200`.
4. `https://blogger.googleusercontent.com/img/a/AVvX=s72-c` becomes
   `…/img/a/AVvX=s1200`, and `…=w640-h480` becomes `…=s1200`.
5. `https://1.bp.blogspot.com/-abc/XYZ/s72-c/k.jpg` becomes `…/s1200/k.jpg`.
6. Non-Blogger URLs are unchanged, including `http://img.test/img.jpg` and a
   lookalike such as `https://example.com/s72-c/a.jpg` and
   `https://blogger.googleusercontent.com.evil.test/img/s72-c/a.jpg`.
7. A Blogger URL without a size token, and one whose filename looks like a token
   (e.g. `…/img/b/X/Y/s1600/s72-c.jpg`), only changes the directory segment; the
   filename is never altered. A query string such as `?x=1` is preserved.
8. `extract_image_from_entry` with `media_thumbnail=[{"url": "<blogger s72-c URL>"}]`
   returns the `s1200` URL, and an entry whose `summary` HTML has a Blogger
   `<img src>` also returns the rewritten URL.
9. The existing `test_extract_image_from_entry` (non-Blogger `media_content`)
   still passes unchanged.
10. The helper is applied idempotently: running it on its own output returns the
    same string.

## Test plan

In `tests/test_lambdas.py`:
- Add a `@pytest.mark.parametrize` test for `upscale_blogger_image_url` covering
  criteria 1–7 and 10. It is a pure function, but importing `lambda_function`
  needs the same env/moto setup as `test_extract_image_from_entry`; reuse that
  setup (or the existing `_scraper_env` helper) rather than adding a new fixture
  style.
- Add a test for criterion 8 next to `test_extract_image_from_entry`, using the
  same `Entry(dict)` shim.
- Run the full CLAUDE.md check list (pytest, black, isort, flake8, mypy).

## Open questions

- Target size: the issue says "e.g. at most 1200 px wide" and "such as `s1200`".
  `s1200` caps the longest side at 1200 px, so a portrait photo would be 1200 px
  tall and narrower. This spec uses `s1200`; switch to `w1200` only if a strict
  width cap is wanted.
