import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlsplit

import boto3
import feedparser
import requests
from bs4 import BeautifulSoup, Tag
from dynamo import (
    get_posts,
    is_new_post,
    is_table_empty,
    mark_sold,
    post_table_name,
    record_notification,
    save_metadata,
    save_post,
)
from stats import count_email_subscriptions

# Constants
BLOG_FEED_URL = "https://atwoodknives.blogspot.com/feeds/posts/default?alt=rss"

SOLD_PATTERNS = [
    r"sold\s*out",
    r"all\s*gone",
    r"gone\s*in\s*a\s*flash",
    r"these\s+are\s+sold\s+out",
    r"thank\s+you",
]
REQUEST_TIMEOUT_S = 10
RECHECK_WINDOW = timedelta(days=7)
MAX_RECHECKS_PER_RUN = 3


def is_sold(text: str) -> bool:
    lines = text.strip().splitlines()
    last_two = lines[-2:] if len(lines) >= 2 else lines
    combined = " ".join(line.lower() for line in last_two)
    return any(re.search(pat, combined) for pat in SOLD_PATTERNS)


def fetch_sold_status(url: str) -> bool:
    response = requests.get(url, timeout=REQUEST_TIMEOUT_S)
    soup = BeautifulSoup(response.text, "html.parser")
    post_body = soup.find("div", class_="post-body")
    post_text = post_body.get_text(separator="\n").strip() if post_body else ""
    return is_sold(post_text)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# SNS (for future use)
sns = boto3.client("sns")
notify_topic_arn = os.environ["NOTIFY_TOPIC_ARN"]


def lambda_handler(event, context):
    feed = feedparser.parse(BLOG_FEED_URL)
    posts = feed.entries

    if not posts:
        print("No posts found.")
        return

    newest = posts[0]
    post_id = newest.get("id")

    if not post_id:
        print("Post has no ID. Skipping.")
        return
    post_url = newest.link
    sold = fetch_sold_status(post_url)

    post = {
        "post_id": post_id,
        "title": newest.get("title", "No title found"),
        "url": newest.get("link", "No URL found"),
        "published": newest.get("published", datetime.now(timezone.utc).isoformat()),
        "image_url": extract_image_from_entry(newest),
        "sold": sold,
    }

    if is_table_empty(post_table_name()):
        print("First run: seeding Posts table without notifications.")
        for entry in posts:
            entry_id = entry.get("id")
            if not entry_id:
                continue

            # Get post content for sold status check
            entry_url = entry.link
            try:
                sold = fetch_sold_status(entry_url)
            except Exception as e:
                print(f"Failed to fetch content for {entry_id}: {e}")
                sold = False

            seed_post = {
                "post_id": entry_id,
                "title": entry.get("title", "No title found"),
                "url": entry.get("link", "No URL found"),
                "published": entry.get(
                    "published", datetime.now(timezone.utc).isoformat()
                ),
                "image_url": extract_image_from_entry(entry),
                "sold": sold,
            }
            save_post(seed_post)
        return

    if is_new_post(post_id):
        print(f"New post detected: {post['title']}")
        save_post(post)
        notify_subscribers(post)
    else:
        print("No new post.")

    recheck_recent_posts(posts, post_id, sold, _utcnow())
    save_metadata(post)


def recheck_recent_posts(entries, newest_id: str, newest_sold: bool, now: datetime):
    """Record sold_at for recent unsold posts that have now sold out.

    Never raises: a failure here must not stop save_metadata.
    """
    try:
        candidates = []
        for entry in entries:
            entry_id = entry.get("id")
            if not entry_id:
                continue
            try:
                published = parsedate_to_datetime(entry.get("published", ""))
            except (TypeError, ValueError):
                continue
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if now - published > RECHECK_WINDOW:
                continue
            candidates.append((published, entry))
        candidates.sort(key=lambda c: c[0], reverse=True)
        if not candidates:
            return

        items = get_posts([entry["id"] for _, entry in candidates])
        sold_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        fetches = 0
        for _, entry in candidates:
            entry_id = entry["id"]
            item = items.get(entry_id)
            if not item or item.get("sold") or item.get("sold_at"):
                continue
            if entry_id == newest_id:
                now_sold = newest_sold
            else:
                if fetches >= MAX_RECHECKS_PER_RUN:
                    continue
                fetches += 1
                try:
                    now_sold = fetch_sold_status(entry.get("link", ""))
                except Exception as e:
                    print(f"Re-check failed for {entry_id}: {e}")
                    continue
            if now_sold:
                try:
                    mark_sold(entry_id, sold_at)
                except Exception as e:
                    print(f"Failed to mark {entry_id} sold: {e}")
    except Exception as e:
        print(f"Re-check of recent posts failed: {e}")


def _first_img_src(html: str) -> str | None:
    """Return the src of the first <img> in the given HTML, if any."""
    img_tag = BeautifulSoup(html, "html.parser").find("img")
    if isinstance(img_tag, Tag):
        src = img_tag.get("src")
        if isinstance(src, str):
            return src
    return None


BLOGGER_IMAGE_SIZE = "s1200"
_BLOGGER_SIZE_TOKEN = re.compile(r"^(s\d+|w\d+|h\d+|w\d+-h\d+)(-[a-z0-9]+)*$")
_BLOGGER_SUFFIX_TOKEN = re.compile(r"=(s\d+|w\d+|h\d+|w\d+-h\d+)(-[a-z0-9]+)*$")
_BLOGGER_HOST = re.compile(
    r"^(blogger\.googleusercontent\.com|[a-z0-9-]+\.bp\.blogspot\.com"
    r"|lh[3-6]\.googleusercontent\.com)$"
)


def upscale_blogger_image_url(url: str | None) -> str | None:
    """Rewrite the size token of a Blogger image URL to BLOGGER_IMAGE_SIZE.

    Handles the path-segment form (``.../s72-c/file.jpg``) and the suffix form
    (``.../AVvX=s72-c``). Non-Blogger URLs and URLs without a size token are
    returned unchanged.
    """
    if not isinstance(url, str) or not url:
        return url
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return url
    if not _BLOGGER_HOST.match(host):
        return url

    path = parts.path
    segments = path.split("/")
    if _BLOGGER_SUFFIX_TOKEN.search(segments[-1]):
        segments[-1] = _BLOGGER_SUFFIX_TOKEN.sub(f"={BLOGGER_IMAGE_SIZE}", segments[-1])
    elif len(segments) >= 2 and _BLOGGER_SIZE_TOKEN.match(segments[-2]):
        segments[-2] = BLOGGER_IMAGE_SIZE
    else:
        return url
    return parts._replace(path="/".join(segments)).geturl()


def extract_image_from_entry(entry) -> str | None:
    return upscale_blogger_image_url(_find_image_url(entry))


def _find_image_url(entry) -> str | None:
    # 1. Try media_content (most common in RSS feeds with media)
    if "media_content" in entry:
        media = entry.media_content
        if media and isinstance(media, list) and "url" in media[0]:
            return media[0]["url"]

    # 2. Try media_thumbnail
    if "media_thumbnail" in entry:
        media = entry.media_thumbnail
        if media and isinstance(media, list) and "url" in media[0]:
            return media[0]["url"]

    # 3. Try to parse 'content' field's HTML and get first <img>
    content_list = entry.get("content", [])
    for content in content_list:
        src = _first_img_src(content.value)
        if src:
            return src

    # 4. Try to parse 'summary' field as fallback
    if "summary" in entry:
        src = _first_img_src(entry.summary)
        if src:
            return src

    # No image found
    return None


SUBJECT_PREFIX = "New Atwood release"
MAX_SUBJECT_LEN = 99


def _safe_image_url(value) -> Optional[str]:
    if isinstance(value, str) and value.startswith("https://"):
        return value
    return None


def build_push_payload(post) -> dict:
    body = post["title"]
    if post.get("sold"):
        body = f"{body} (already sold out)"
    return {
        "title": SUBJECT_PREFIX,
        "body": body,
        "url": post["url"],
        "image_url": _safe_image_url(post.get("image_url")),
    }


def build_email_subject(title: str) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    )
    clean = re.sub(r"[\s\x00-\x1f\x7f]+", " ", ascii_title).strip()
    subject = f"{SUBJECT_PREFIX}: {clean}" if clean else SUBJECT_PREFIX
    if len(subject) > MAX_SUBJECT_LEN:
        subject = subject[: MAX_SUBJECT_LEN - 3].rstrip() + "..."
    return subject


def build_email_body(post) -> str:
    status = "Sold out" if post.get("sold") else "Available"
    return f"{SUBJECT_PREFIX}: {post['title']}\n\n{post['url']}\n\nStatus: {status}\n"


def build_sns_message(post) -> str:
    push_json = json.dumps(build_push_payload(post))
    return json.dumps(
        {"default": push_json, "email": build_email_body(post), "lambda": push_json}
    )


def notify_subscribers(post):
    try:
        sns.publish(
            TopicArn=notify_topic_arn,
            Subject=build_email_subject(post["title"]),
            Message=build_sns_message(post),
            MessageStructure="json",
        )
        print("Notification sent.")
    except Exception as e:
        print(f"Failed to send notification: {e}")
        return

    try:
        confirmed, _ = count_email_subscriptions(sns, notify_topic_arn)
        record_notification(confirmed, datetime.now(timezone.utc))
    except Exception as e:
        print(f"Failed to record notification stats: {e}")
