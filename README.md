# 🗡️ Atwood Blog Monitor

A serverless AWS-hosted web app that monitors [atwoodknives.blogspot.com](https://atwoodknives.blogspot.com/) for new blog posts, stores and serves post data, and allows users to subscribe for notifications — including push notifications to browsers.

---

## 🌐 Features

- ✅ Monitors Atwood blog every minute via scheduled Lambda
- ✅ Detects and stores new posts in DynamoDB
- ✅ Notifies subscribers via SNS
- ✅ Exposes public status and subscription APIs via API Gateway
- ✅ Allows users to register for web push notifications
- ✅ Serves a modern Elm frontend from S3 via CloudFront (with HTTPS + custom domain)
- ✅ Includes CloudWatch dashboard to monitor push delivery

---

## 📦 Architecture

### AWS Resources

| Component         | Purpose                                                  |
|------------------|----------------------------------------------------------|
| **Lambda**        | Blog scraper, status API, user subscription handlers     |
| **DynamoDB**      | Posts, users, web push subscriptions                     |
| **SNS**           | Notifies subscribers                                     |
| **S3 + CloudFront** | Hosts and serves the Elm frontend                       |
| **API Gateway**   | Public endpoints for `/status`, `/subscribe`, etc.      |
| **ACM + Route53** | HTTPS certificate and DNS via `atwood-sniper.com`       |
| **CloudWatch**    | Custom metrics for push success/failure                  |

---

## 🚀 Deployment

### Prerequisites

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
- [CDK CLI](https://docs.aws.amazon.com/cdk/latest/guide/work-with-cdk-python.html)
- AWS Account with Route53 hosted zone for `atwood-sniper.com`
- Bootstrap your environment:

```sh
cdk bootstrap aws://<account>/<region>
```

### Environment Secrets

Store VAPID secrets in **SSM Parameter Store**:

```sh
aws ssm put-parameter --name "/atwood/vapid_private_key" --value "..." --type "SecureString"
aws ssm put-parameter --name "/atwood/vapid_public_key" --value "..." --type "String"
```

### Build and Deploy

```bash
# Install dependencies
pip install -r requirements.txt

# Build the Lambda layer
# (installs deps from layer/requirements.txt using Docker and
# generates out/layer.zip)
./build-layer-with-docker.sh

# Deploy the stack
cdk deploy
```

### Frontend

```bash
cd elm-frontend
npm ci
./build.sh  # builds Elm and Tailwind CSS
```

---

## 🔔 Testing Push Notifications (staging)

```bash
AWS_PROFILE=my-profile scripts/send-test-push.sh
scripts/send-test-push.sh --title "Test release" --image-url https://example.com/a.jpg \
  --url https://atwoodknives.blogspot.com/ --sold
```

Invokes the staging push Lambda (`atwood-staging-web-push`, `us-west-2`) directly
with an SNS-style event, so it **sends to every staging push subscriber** but
does not publish to the SNS topic (no emails). By default it uses the latest post
(including image) from the staging `/status` endpoint; `--title`, `--image-url`,
`--url` and `--sold` override it. Production is refused. Needs the `aws` CLI,
`curl` and `python3`.

---

## 📂 Project Structure

```
.
├── lambda/                     # Lambda handler code
│   ├── lambda_function.py      # Blog scraper
│   ├── status_lambda.py        # Status API
│   ├── subscribe_lambda.py     # User subscription
│   └── lambda-docker/          # Web Push Dockerized Lambda
├── scripts/                    # Deploy and helper scripts (e.g. send-test-push.sh)
├── elm-frontend/               # Elm frontend app
├── atwood_monitor/            # CDK application
│   ├── __init__.py
│   ├── stack.py                # CDK Stack (entrypoint)
│   ├── lambdas.py              # Lambda creation utilities
│   ├── api_gateway.py
│   ├── storage.py
│   ├── frontend.py
│   └── monitoring.py
└── README.md
```

---

## 🔐 Security Notes

- Secrets are stored securely in **SSM Parameter Store**
- CloudFront is restricted via **Origin Access Identity**
- Lambda role is scoped to minimal IAM policies
- CORS handled properly on all public endpoints

---

## 🧪 API Endpoints

- `GET /status` — JSON status of last check and last post
- `POST /subscribe` — Register an email/SNS subscription
- `POST /register-subscription` — Store web push subscription

---

## 📈 Monitoring

View the CloudWatch dashboard `WebPushDashboard` to monitor:

- ✅ Push successes
- ❌ Push failures

---

## 🤝 Contributing

Pull requests and issues are welcome. For major changes, please open an issue first to discuss what you’d like to change.

---

## 🛠️ Git Hooks

Run `./scripts/install-git-hooks.sh` once to install local git hooks. The `pre-commit` hook formats Python files using **black** and **isort** before they are committed. This keeps commits passing the CI formatting checks.

---

## 📄 License

MIT — see `LICENSE` file.
