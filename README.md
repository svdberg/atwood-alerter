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

# Build Lambda layers (if needed)
# e.g., pip install feedparser -t out/layer/python

# Deploy the stack
cdk deploy
```

### Frontend

```bash
cd elm-frontend
npm install
./build.sh  # builds Elm and Tailwind CSS
```

---

## 📂 Project Structure

```
.
├── lambda/                     # Lambda handler code
│   ├── lambda_function.py      # Blog scraper
│   ├── status_lambda.py        # Status API
│   ├── subscribe_lambda.py     # User subscription
│   └── lambda-docker/          # Web Push Dockerized Lambda
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

## 📄 License

MIT — see `LICENSE` file.
