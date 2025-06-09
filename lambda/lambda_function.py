import os
import boto3
import feedparser
from datetime import datetime, timezone
from dynamo import is_new_post, save_post, save_metadata, is_table_empty, post_table_name
from bs4 import BeautifulSoup
import json


# Constants
BLOG_FEED_URL = "https://atwoodknives.blogspot.com/feeds/posts/default?alt=rss"

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

    post = {
        "post_id": post_id,
        "title": newest.get("title", "No title found"),
        "url": newest.get("link", "No URL found"),
        "published": newest.get("published", datetime.now(timezone.utc).isoformat()),
        "image_url": extract_image_from_entry(newest)
    }

    if is_table_empty(post_table_name()):
        print("First run: seeding Posts table without notifications.")
        for post in posts:
            save_post(post)
        return

    if is_new_post(post_id):
        print(f"New post detected: {post['title']}")
        save_post(post)
        notify_subscribers(post)
    else:
        print("No new post.")

    save_metadata(post)


def extract_image_from_entry(entry) -> str | None:
    # 1. Try media_content (most common in RSS feeds with media)
    if 'media_content' in entry:
        media = entry.media_content
        if media and isinstance(media, list) and 'url' in media[0]:
            return media[0]['url']

    # 2. Try media_thumbnail
    if 'media_thumbnail' in entry:
        media = entry.media_thumbnail
        if media and isinstance(media, list) and 'url' in media[0]:
            return media[0]['url']

    # 3. Try to parse 'content' field's HTML and get first <img>
    content_list = entry.get('content', [])
    for content in content_list:
        soup = BeautifulSoup(content.value, "html.parser")
        img_tag = soup.find("img")
        if img_tag and img_tag.has_attr("src"):
            return img_tag['src']

    # 4. Try to parse 'summary' field as fallback
    if 'summary' in entry:
        soup = BeautifulSoup(entry.summary, "html.parser")
        img_tag = soup.find("img")
        if img_tag and img_tag.has_attr("src"):
            return img_tag['src']

    # No image found
    return None


def notify_subscribers(post):
    message = {
        "title": "New Blog Post!",
        "body": post['title'],
        "url": post['url']
    }

    try:
        sns.publish(
            TopicArn=notify_topic_arn,
            Subject="New Blog Post",
            Message=json.dumps(message),  # Send as JSON string
        )
        print("Notification sent.")
    except Exception as e:
        print(f"Failed to send notification: {e}")
