FROM public.ecr.aws/lambda/python:3.11

# Copy your function code
COPY web_push_lambda.py ${LAMBDA_TASK_ROOT}

# Install dependencies into Lambda task root
RUN pip install pywebpush boto3 -t ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD ["web_push_lambda.lambda_handler"]
