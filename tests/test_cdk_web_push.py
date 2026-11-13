import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aws_cdk import App, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_sns as sns
from aws_cdk.assertions import Template

from atwood_monitor.environments import EnvironmentConfig
from atwood_monitor.lambdas import create_web_push_lambda

ROOT = os.path.join(os.path.dirname(__file__), "..")
DOCKER_DIR = os.path.join(ROOT, "lambda", "lambda-docker")


def test_web_push_lambda_memory_and_identity():
    cwd = os.getcwd()
    os.chdir(ROOT)  # the image asset path is relative to the repo root
    try:
        app = App(outdir=None)
        stack = Stack(app, "TestStack")
        env_config = EnvironmentConfig(
            name="staging",
            account="123456789012",
            region="us-west-2",
            domain_name="example.com",
        )
        table = dynamodb.Table(
            stack,
            "T",
            partition_key=dynamodb.Attribute(
                name="subscription_id", type=dynamodb.AttributeType.STRING
            ),
        )
        topic = sns.Topic(stack, "Topic")
        create_web_push_lambda(stack, table, topic, env_config)
        template = Template.from_stack(stack)
    finally:
        os.chdir(cwd)

    fns = template.find_resources(
        "AWS::Lambda::Function",
        {"Properties": {"PackageType": "Image"}},
    )
    assert len(fns) == 1
    logical_id, fn = next(iter(fns.items()))
    assert logical_id.startswith("WebPushLambda")
    props = fn["Properties"]
    assert props["MemorySize"] == 512
    assert props["Timeout"] == 30
    assert props["FunctionName"] == f"{env_config.resource_name_prefix}-web-push"


def test_docker_requirements_pinned():
    with open(os.path.join(DOCKER_DIR, "requirements.txt")) as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    assert lines and all("==" in ln for ln in lines)
    names = {ln.split("==")[0].lower() for ln in lines}
    assert {"cryptography", "py-vapid", "http-ece", "requests"} <= names
    assert "boto3" not in names
    assert "pywebpush==2.5.0" in lines
    with open(os.path.join(DOCKER_DIR, "Dockerfile")) as f:
        installs = [ln for ln in f if "pip install" in ln]
    assert len(installs) == 1 and "-r requirements.txt" in installs[0]
