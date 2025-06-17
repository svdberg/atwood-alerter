#!/usr/bin/env python3
"""
Post-deployment verification script for Atwood Monitor.
Runs health checks and smoke tests against the deployed environment.
"""

import os
import sys
import time
from typing import Optional

import requests


def get_api_endpoint() -> Optional[str]:
    """Get API endpoint from environment or CDK outputs."""
    # Try environment variable first
    endpoint = os.environ.get('API_ENDPOINT')
    if endpoint:
        return endpoint

    # Try to get from CDK outputs
    try:
        import json
        env = os.environ.get('ENVIRONMENT', 'development')
        outputs_file = f"{env}-outputs.json"

        if os.path.exists(outputs_file):
            with open(outputs_file, 'r') as f:
                outputs = json.load(f)
                return outputs.get('ApiEndpoint')
    except Exception as e:
        print(f"Could not read CDK outputs: {e}")

    # Fallback based on environment
    env = os.environ.get('ENVIRONMENT', 'development')
    if env == 'production':
        return 'https://api.atwood-sniper.com'
    elif env == 'staging':
        return 'https://api.staging.atwood-sniper.com'
    else:
        return 'https://api.dev.atwood-sniper.com'


def health_check(endpoint: str, timeout: int = 30) -> bool:
    """Perform health check on deployed service."""
    print(f"🏥 Running health check against {endpoint}")

    try:
        response = requests.get(f"{endpoint}/status", timeout=timeout)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check passed - Last check: {data.get('last_check', 'N/A')}")
            return True
        else:
            print(f"❌ Health check failed - Status: {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        print(f"❌ Health check timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def smoke_test(endpoint: str) -> bool:
    """Run smoke tests against deployed service."""
    print(f"🧪 Running smoke tests against {endpoint}")

    tests = [
        {
            "name": "Status endpoint returns 200",
            "method": "GET",
            "path": "/status",
            "expected_status": 200,
            "expected_keys": ["last_check", "status"]
        },
        {
            "name": "Subscribe endpoint validation",
            "method": "POST",
            "path": "/subscribe",
            "data": {},
            "expected_status": 400  # Should fail without valid email
        },
        {
            "name": "Register web push validation",
            "method": "POST",
            "path": "/register-subscription",
            "data": {},
            "expected_status": 400  # Should fail without valid subscription data
        }
    ]

    for test in tests:
        try:
            print(f"  🔍 {test['name']}")

            if test["method"] == "GET":
                response = requests.get(f"{endpoint}{test['path']}")
            elif test["method"] == "POST":
                response = requests.post(
                    f"{endpoint}{test['path']}",
                    json=test.get("data", {})
                )

            if response.status_code != test["expected_status"]:
                print(f"    ❌ Expected status {test['expected_status']}, got {response.status_code}")
                return False

            # Check for expected keys in response
            if "expected_keys" in test and response.status_code == 200:
                try:
                    data = response.json()
                    for key in test["expected_keys"]:
                        if key not in data:
                            print(f"    ❌ Missing expected key '{key}' in response")
                            return False
                except:
                    print(f"    ❌ Response is not valid JSON")
                    return False

            print(f"    ✅ Passed")

        except Exception as e:
            print(f"    ❌ Test failed: {e}")
            return False

    print("✅ All smoke tests passed")
    return True


def performance_check(endpoint: str) -> bool:
    """Check basic performance metrics."""
    print(f"⚡ Running performance checks against {endpoint}")

    try:
        start_time = time.time()
        requests.get(f"{endpoint}/status")
        response_time = time.time() - start_time

        if response_time > 5.0:
            print(f"⚠️  Slow response time: {response_time:.2f}s (expected < 5s)")
            return False

        print(f"✅ Response time: {response_time:.2f}s")
        return True

    except Exception as e:
        print(f"❌ Performance check failed: {e}")
        return False


def domain_check(domain: str) -> bool:
    """Check if domain is accessible via HTTPS."""
    print(f"🌐 Checking domain accessibility: {domain}")

    try:
        response = requests.get(f"https://{domain}", timeout=10)

        if response.status_code == 200:
            print(f"✅ Domain {domain} is accessible")
            return True
        else:
            print(f"❌ Domain returned status {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Domain check failed: {e}")
        return False


def main():
    """Main verification routine."""
    print("🔍 Starting post-deployment verification...")

    # Get environment
    env = os.environ.get('ENVIRONMENT', 'development')
    print(f"Environment: {env}")

    # Get API endpoint
    endpoint = get_api_endpoint()
    if not endpoint:
        print("❌ Could not determine API endpoint")
        sys.exit(1)

    print(f"API Endpoint: {endpoint}")

    # Wait for deployment to stabilize
    print("⏳ Waiting 30 seconds for deployment to stabilize...")
    time.sleep(30)

    # Run verification steps
    checks = [
        ("Health Check", lambda: health_check(endpoint)),
        ("Smoke Tests", lambda: smoke_test(endpoint)),
        ("Performance Check", lambda: performance_check(endpoint))
    ]

    # Add domain check for non-dev environments
    if env != 'development':
        domain_map = {
            'staging': 'staging.atwood-sniper.com',
            'production': 'atwood-sniper.com'
        }
        domain = domain_map.get(env)
        if domain:
            checks.append(("Domain Check", lambda: domain_check(domain)))

    # Execute all checks
    failed_checks = []
    for check_name, check_func in checks:
        try:
            if not check_func():
                failed_checks.append(check_name)
        except Exception as e:
            print(f"❌ {check_name} threw exception: {e}")
            failed_checks.append(check_name)

    # Report results
    if failed_checks:
        print(f"\n❌ Verification failed! Failed checks: {', '.join(failed_checks)}")
        sys.exit(1)
    else:
        print(f"\n✅ All verification checks passed for {env} environment!")
        print("🎉 Deployment verification successful!")


if __name__ == "__main__":
    main()
