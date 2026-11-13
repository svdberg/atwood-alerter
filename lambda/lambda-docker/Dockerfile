FROM public.ecr.aws/lambda/python:3.11

# Copy your function code
COPY web_push_lambda.py ${LAMBDA_TASK_ROOT}

# Install pinned dependencies into Lambda task root (boto3 comes with the base image)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -t ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD ["web_push_lambda.lambda_handler"]
