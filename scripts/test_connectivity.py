#!/usr/bin/env python3
"""End-to-end connectivity test for Seishin infrastructure.

From laptop (with Tailscale active):
    SEI_HOST=<SERVER_IP> python test_connectivity.py

Local testing:
    python test_connectivity.py
"""
import asyncio
import os
import sys

HOST = os.environ.get("SEI_HOST", "127.0.0.1")
PORT = int(os.environ.get("SEI_PORT", "5052"))
TOKEN = os.environ.get("SEI_AUTH_TOKEN", "test-token-change-me")


async def test():
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus

    uri = f"ws://{HOST}:{PORT}"
    passed = 0
    failed = 0

    # Test 1: Valid token
    print(f"[TEST 1] Connect with valid token to {uri}")
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with connect(uri, additional_headers=headers) as ws:
            await ws.send("hello from test client")
            response = await ws.recv()
            assert response == "echo: hello from test client", f"Expected echo, got: {response}"
            print(f"  PASS: Got response: {response}")
            passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # Test 2: Wrong token — should get HTTP 401
    print(f"[TEST 2] Connect with wrong token (expect 401)")
    try:
        headers = {"Authorization": "Bearer wrong-token"}
        async with connect(uri, additional_headers=headers) as ws:
            print(f"  FAIL: Connection should have been rejected")
            failed += 1
    except InvalidStatus as e:
        if e.response.status_code == 401:
            print(f"  PASS: Correctly rejected with 401")
            passed += 1
        else:
            print(f"  FAIL: Expected 401, got {e.response.status_code}")
            failed += 1
    except Exception as e:
        print(f"  FAIL: Unexpected error: {e}")
        failed += 1

    # Test 3: No token — should get HTTP 401
    print(f"[TEST 3] Connect with no token (expect 401)")
    try:
        async with connect(uri) as ws:
            print(f"  FAIL: Connection should have been rejected")
            failed += 1
    except InvalidStatus as e:
        if e.response.status_code == 401:
            print(f"  PASS: Correctly rejected with 401")
            passed += 1
        else:
            print(f"  FAIL: Expected 401, got {e.response.status_code}")
            failed += 1
    except Exception as e:
        print(f"  FAIL: Unexpected error: {e}")
        failed += 1

    print(f"\nResults: {passed}/{passed + failed} passed")
    if failed > 0:
        sys.exit(1)
    print("All connectivity tests PASSED")


if __name__ == "__main__":
    asyncio.run(test())
