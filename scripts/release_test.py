#!/usr/bin/env python3
"""
Genesis Protocol v1.0 - Release Test Script

Tests all critical endpoints for release verification.

Usage:
    python scripts/release_test.py [--url https://genesis-protocol-00a1.up.railway.app]
"""

import sys
import json
import argparse
import requests
from datetime import datetime


def test_endpoint(url: str, path: str, expected_fields: list = None) -> tuple:
    """Test a single endpoint."""
    try:
        response = requests.get(f"{url}{path}", timeout=10)
        if response.status_code == 200:
            try:
                data = response.json()
                if expected_fields:
                    missing = [f for f in expected_fields if f not in data]
                    if missing:
                        return False, f"Missing fields: {missing}"
                return True, data
            except json.JSONDecodeError:
                return False, "Not JSON response"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, str(e)


def run_tests(url: str) -> bool:
    """Run all release tests."""
    print("=" * 60)
    print("Genesis Protocol v1.0 - Release Tests")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Time: {datetime.now().isoformat()}")
    print()
    
    all_passed = True
    results = []
    
    # Test 1: Health
    print("[1/5] Testing /api/health...")
    passed, data = test_endpoint(url, "/api/health")
    if passed:
        print(f"   ✓ PASS: {data.get('status', 'unknown')}")
    else:
        print(f"   ✗ FAIL: {data}")
        all_passed = False
    results.append(("health", passed))
    
    # Test 2: Version
    print("[2/5] Testing /api/version...")
    passed, data = test_endpoint(url, "/api/version", ['version', 'build_date'])
    if passed:
        print(f"   ✓ PASS: v{data.get('version', '?')} ({data.get('build_date', '?')})")
    else:
        print(f"   ✗ FAIL: {data}")
        all_passed = False
    results.append(("version", passed))
    
    # Test 3: Status
    print("[3/5] Testing /api/status...")
    passed, data = test_endpoint(url, "/api/status", ['metrics', 'status'])
    if passed:
        metrics = data.get('metrics', {})
        print(f"   ✓ PASS: Requests={metrics.get('request_count', 0)}, Errors={metrics.get('error_count', 0)}")
    else:
        print(f"   ✗ FAIL: {data}")
        all_passed = False
    results.append(("status", passed))
    
    # Test 4: Diagnostics
    print("[4/5] Testing /api/diagnostics...")
    passed, data = test_endpoint(url, "/api/diagnostics", ['version', 'providers', 'database'])
    if passed:
        providers = data.get('providers', {}).get('available', [])
        db_status = data.get('database', {}).get('status', 'unknown')
        print(f"   ✓ PASS: Providers={providers}, DB={db_status}")
    else:
        print(f"   ✗ FAIL: {data}")
        all_passed = False
    results.append(("diagnostics", passed))
    
    # Test 5: Debug
    print("[5/5] Testing /api/debug...")
    passed, data = test_endpoint(url, "/api/debug", ['available_providers', 'provider_status'])
    if passed:
        providers = data.get('available_providers', [])
        groq = data.get('groq_configured', False)
        print(f"   ✓ PASS: Available={providers}, Groq configured={groq}")
    else:
        print(f"   ✗ FAIL: {data}")
        all_passed = False
    results.append(("debug", passed))
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name:15} {status}")
    
    print()
    if all_passed:
        print("✓ ALL TESTS PASSED - Release Ready")
        return True
    else:
        print("✗ SOME TESTS FAILED - Review Required")
        return False


def main():
    parser = argparse.ArgumentParser(description="Genesis Protocol Release Test")
    parser.add_argument("--url", default="https://genesis-protocol-00a1.up.railway.app",
                       help="Base URL of the deployment")
    args = parser.parse_args()
    
    success = run_tests(args.url)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
