#!/usr/bin/env bash
#
# send-test-push.sh - send a test web push notification to STAGING subscribers.
#
# Invokes the staging push Lambda (atwood-staging-web-push) directly with an
# SNS-style event. It does NOT publish to the SNS topic, so email subscribers
# are not notified. The event's Message is the same push JSON that
# notify_subscribers puts in the SNS "lambda" protocol entry:
#   {"title", "body", "url", "image_url"}
#
# WARNING: this sends to EVERY staging push subscriber.
#
# Usage:
#   scripts/send-test-push.sh [--title TEXT] [--image-url URL] [--url URL] [--sold]
#
# By default the latest post (title, url, image) is read from the staging
# /status endpoint. Overrides:
#   --title TEXT      Post title (becomes the notification body)
#   --image-url URL   Release image (https:// only)
#   --url URL         Post URL opened by the notification
#   --sold            Mark as sold out (appends " (already sold out)")
#   -h, --help        Show this help
#
# Environment:
#   AWS_PROFILE       Optional; local AWS profile to use
#   STATUS_URL        Override the status endpoint (default: the ApiEndpoint
#                     output of the AtwoodMonitor-Staging-Main stack + "status")
#   Region is fixed to us-west-2 (staging). Production is refused.
#
# Requires: aws CLI, curl, python3.

set -euo pipefail

REGION="us-west-2"
ENVIRONMENT="${ENVIRONMENT:-staging}"
FUNCTION_NAME="${FUNCTION_NAME:-atwood-staging-web-push}"
STACK_NAME="AtwoodMonitor-Staging-Main"
STATUS_URL="${STATUS_URL:-}"

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }

# Staging only: refuse anything that looks like production.
if [[ "$ENVIRONMENT" != "staging" || "$FUNCTION_NAME" != "atwood-staging-web-push" \
      || "$FUNCTION_NAME" == *prod* || "$STATUS_URL" == *eu-north-1* ]]; then
  echo "Refusing to run: staging only (ENVIRONMENT=$ENVIRONMENT, FUNCTION_NAME=$FUNCTION_NAME)." >&2
  exit 1
fi

TITLE="" IMAGE_URL="" POST_URL="" SOLD="false"
HAVE_TITLE=0 HAVE_IMAGE=0 HAVE_URL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)     [[ $# -ge 2 ]] || { echo "--title needs a value" >&2; exit 2; }
                 TITLE="$2"; HAVE_TITLE=1; shift 2 ;;
    --image-url) [[ $# -ge 2 ]] || { echo "--image-url needs a value" >&2; exit 2; }
                 IMAGE_URL="$2"; HAVE_IMAGE=1; shift 2 ;;
    --url)       [[ $# -ge 2 ]] || { echo "--url needs a value" >&2; exit 2; }
                 POST_URL="$2"; HAVE_URL=1; shift 2 ;;
    --sold)      SOLD="true"; shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Fetch the latest post from staging /status unless everything is overridden.
if (( ! (HAVE_TITLE && HAVE_IMAGE && HAVE_URL) )); then
  if [[ -z "$STATUS_URL" ]]; then
    API_URL="$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK_NAME" \
      --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)" || {
      echo "Could not read ApiEndpoint from $STACK_NAME; set STATUS_URL or pass --title, --image-url and --url." >&2
      exit 1
    }
    STATUS_URL="${API_URL%/}/status"
  fi
  echo "Fetching latest post from $STATUS_URL ..."
  STATUS_JSON="$(curl -fsS --max-time 15 "$STATUS_URL")" || {
    echo "Could not fetch $STATUS_URL; pass --title, --image-url and --url." >&2
    exit 1
  }
  # Emit shell-safe, NUL-free fields: title, url, image_url (one per line).
  mapfile -t FIELDS < <(printf '%s' "$STATUS_JSON" | python3 -c '
import json, sys
p = (json.load(sys.stdin).get("last_seen_post") or {})
for k in ("title", "url", "image_url"):
    print(" ".join(str(p.get(k) or "").split()))
')
  (( HAVE_TITLE )) || TITLE="${FIELDS[0]:-}"
  (( HAVE_URL ))   || POST_URL="${FIELDS[1]:-}"
  (( HAVE_IMAGE )) || IMAGE_URL="${FIELDS[2]:-}"
fi

if [[ -z "$TITLE" || -z "$POST_URL" ]]; then
  echo "No post title/url available; pass --title and --url." >&2
  exit 1
fi

# Build the event: SNS record whose Message is the push payload JSON.
EVENT_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"
trap 'rm -f "$EVENT_FILE" "$RESPONSE_FILE"' EXIT

TITLE="$TITLE" POST_URL="$POST_URL" IMAGE_URL="$IMAGE_URL" SOLD="$SOLD" \
python3 - >"$EVENT_FILE" <<'PY'
import json, os

title = os.environ["TITLE"]
if os.environ["SOLD"] == "true":
    title += " (already sold out)"
image = os.environ["IMAGE_URL"]
# Mirrors lambda_function.build_push_payload: https images only, else null.
payload = {
    "title": "New Atwood release",
    "body": title,
    "url": os.environ["POST_URL"],
    "image_url": image if image.startswith("https://") else None,
}
print(json.dumps({"Records": [{"EventSource": "aws:sns",
                               "Sns": {"Message": json.dumps(payload)}}]}))
PY

echo
echo "WARNING: this sends a push notification to EVERY staging push subscriber."
echo "Function: $FUNCTION_NAME ($REGION). SNS topic is NOT used; no emails are sent."
echo "Payload:"
python3 -c 'import json,sys; print(json.dumps(json.loads(json.load(open(sys.argv[1]))["Records"][0]["Sns"]["Message"]), indent=2))' "$EVENT_FILE"
echo

aws lambda invoke \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --cli-binary-format raw-in-base64-out \
  --payload "file://$EVENT_FILE" \
  --log-type Tail \
  --query '{StatusCode: StatusCode, FunctionError: FunctionError, ExecutedVersion: ExecutedVersion}' \
  --output json \
  "$RESPONSE_FILE"

echo
echo "Lambda response:"
cat "$RESPONSE_FILE"
echo

if grep -q '"errorMessage"' "$RESPONSE_FILE"; then
  echo "Lambda reported an error." >&2
  exit 1
fi
