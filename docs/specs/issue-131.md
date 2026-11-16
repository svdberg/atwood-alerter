# Spec: Timeouts for scraper HTTP requests (#131)

## Problem

The scraper Lambda (`lambda/lambda_function.py`, 30 s timeout set in
`atwood_monitor/lambdas.py`, runs on a schedule) makes outbound HTTP calls that
can stall until Lambda kills the run. `feedparser.parse(BLOG_FEED_URL)`
downloads the feed itself with no timeout. `fetch_sold_status` already passes
`timeout=REQUEST_TIMEOUT_S` (a single 10 s value) but doesn't check the status
code. The newest-post call in `lambda_handler` (`sold = fetch_sold_status(post_url)`)
has no `try/except`, so a slow or failing post page crashes the run before
the new post is saved or announced. Getting the alert out is the product's
core value, so a slow post page must never block it. A failed feed fetch should
also leave `__meta__` unchanged so that "last checked" shows the run failed.

## Scope

In scope:
- `lambda/lambda_function.py`: a timeout constant, a shared GET helper, fetching
  the feed with `requests`, making the newest-post sold check fail-safe, and a
  time-budget guard on post-page fetches.
- `tests/test_lambdas.py`: new tests, plus updates to the existing scraper
  helpers that monkeypatch `feedparser.parse` and `requests.get`.

Out of scope:
- CDK and infra. The Lambda timeout, schedule and memory stay as they are.
  `atwood_monitor/storage.py` is not touched.
- `lambda/dynamo.py` and the `__meta__` schema.
- Retries and backoff. The next scheduled run is the retry.
- Feed parse errors (`bozo`). The existing "No posts found." early return
  stays as it is.
- No new runtime dependencies (`requests` and `feedparser` are already used).

## Design

All changes are in `lambda/lambda_function.py`.

1. **Constants.** Replace `REQUEST_TIMEOUT_S = 10` with
   `REQUEST_TIMEOUT = (3, 10)`, a `(connect, read)` tuple in seconds. Add
   `FETCH_RESERVE_S = 5`, the time kept free for DynamoDB and SNS after the last
   fetch.
2. **Shared helper** `http_get(url: str) -> requests.Response`. It calls
   `requests.get(url, timeout=REQUEST_TIMEOUT)` and then
   `response.raise_for_status()`. It raises `requests.RequestException` on a
   timeout, a connection error or a non-2xx status. Every outbound call goes
   through this helper, and nothing else in the module calls `requests.get`.
3. **`fetch_sold_status(url)`** uses `http_get`. Its behaviour is otherwise
   unchanged, and it still raises on failure.
4. **Feed fetch.** Add `fetch_feed()`, which calls `http_get(BLOG_FEED_URL)` and
   returns `feedparser.parse(response.content)` (pass bytes, so feedparser
   handles the encoding). In `lambda_handler`, wrap the call in
   `try/except requests.RequestException`. On failure it prints
   `Feed fetch failed: <exc>` and returns. It doesn't call `save_metadata`,
   `save_post` or `notify_subscribers`, and it doesn't fetch any post page.
5. **Newest-post sold check.** Wrap it in `try/except Exception` (in the same
   way as the seed loop). On failure, print
   `Sold check failed for <post_id>: <exc>` and use `sold = False`. The run
   then continues as usual: the new-post detection, `save_post`,
   `notify_subscribers`, the recheck and `save_metadata` all still happen.
6. **Time budget.** The worst case with no guard is 5 fetches × 13 s = 65 s,
   which is more than the 30 s timeout. Add
   `_has_time_for_fetch(context) -> bool`. It returns `True` when `context` is
   `None` or has no `get_remaining_time_in_millis` (this keeps the tests and
   local runs simple). Otherwise it returns
   `remaining_ms / 1000 >= sum(REQUEST_TIMEOUT) + FETCH_RESERVE_S` (18 s).
   Check it before every **post-page** fetch. The feed fetch always runs.
   - Newest post: if there isn't enough time, skip the fetch, print
     `Skipping sold check for <post_id>: low time budget` and use `sold = False`.
   - Seed loop: if there isn't enough time, skip the fetch for that entry and
     save it with `sold = False`.
   - `recheck_recent_posts`: add an optional `context=None` parameter. If
     there isn't enough time, stop doing further page fetches (the newest-post
     shortcut, which doesn't fetch, still applies) and print one line.
   With this guard, the last fetch starts with at least 18 s left, so it ends
   with at least 5 s left for DynamoDB and SNS. Caveat: the read timeout applies
   to each socket read, not to the whole response. A server that trickles bytes
   can still run longer, but that is an edge case and is accepted here.

Guardrails: no changes to `storage.py`, resource names, `ci-cd.yml` or
`layer/requirements.txt`.

## Acceptance criteria

1. `REQUEST_TIMEOUT == (3, 10)`. `http_get` passes exactly this tuple as
   `timeout=` to `requests.get` and calls `raise_for_status()`.
2. `fetch_sold_status` and the feed fetch both go through `http_get`. A test
   that records `requests.get` calls during one handler run sees
   `timeout == REQUEST_TIMEOUT` on every call, including the recheck fetches.
3. `feedparser.parse` gets the response body (`bytes`), not `BLOG_FEED_URL`.
4. If the feed GET raises `requests.Timeout`, the handler returns without an
   exception. `save_metadata`, `save_post` and `notify_subscribers` are not
   called, no post-page GET happens, and stdout contains `Feed fetch failed`.
5. Same as AC4 for `requests.ConnectionError` and for a non-2xx response that
   makes `raise_for_status` raise `requests.HTTPError`. An existing `__meta__`
   item in DynamoDB stays unchanged.
6. If the newest post is new and its page GET raises `requests.Timeout`, the
   post is saved with `sold == False`, `notify_subscribers` is called once with
   `sold == False`, `save_metadata` is called, and stdout contains
   `Sold check failed`.
7. With a fake context whose `get_remaining_time_in_millis()` returns
   `17_000`, no post-page GET happens. A new newest post is still saved and
   notified with `sold == False`, and `save_metadata` is called.
8. With remaining time of `60_000`, the newest-post check and up to
   `MAX_RECHECKS_PER_RUN` recheck fetches happen as they do today.
9. With `context=None`, the behaviour matches AC8 (no budget limit).
10. The seed run with a low time budget saves every entry with `sold == False`
    and makes no post-page GET.
11. The existing scraper tests still pass after their fakes are updated (the
    feed now comes through `requests.get`).

## Test plan

In `tests/test_lambdas.py`, use `@mock_aws` and the existing `_scraper_env()`:
- Update `_setup_recheck`, `test_seed_run_has_no_sold_at_and_no_rechecks` and
  `test_fetch_sold_status_uses_timeout`. The fake response needs `content`,
  `text` and `raise_for_status()`, and `fake_get` has to serve the feed URL. The
  simplest option is to monkeypatch `mod.fetch_feed` (or `mod.http_get`)
  instead of `feedparser.parse`. Fix the seed call count, which is currently
  `1 + 2`.
- New: `test_http_get_uses_timeout_tuple_and_raises_for_status` (AC1).
- New: `test_feed_fetch_parses_response_content` (AC3).
- New: `test_feed_timeout_skips_metadata` with a parametrized
  `Timeout`/`ConnectionError`/HTTP 503 (AC4, AC5).
- New: `test_newest_sold_check_timeout_still_notifies` (AC6).
- New: `test_low_time_budget_skips_page_fetches`, which uses a stub context
  class (AC7). Also add a seed-run variant (AC10).
- New: `test_all_requests_use_timeout` (AC2, AC8).

## Open questions

- Fetching with `requests` changes the User-Agent from feedparser's to
  `python-requests/x`. Blogger has served the feed fine to generic clients so
  far, but it isn't known whether it treats this UA any differently. Should
  `http_get` send an explicit UA (e.g. `atwood-alerter/1.0`)?
