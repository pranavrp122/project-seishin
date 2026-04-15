#!/usr/bin/env python3
"""WebSocket echo server with Bearer token authentication.

Validates end-to-end connectivity: Laptop -> Tailscale VPN -> WSL2 -> this server.
Auth pattern here becomes the template for Sei Engine (Phase 2).

Usage:
    SEI_AUTH_TOKEN=your-secret python scripts/echo_server.py
"""
import asyncio
import os
from http import HTTPStatus
from websockets.asyncio.server import serve

AUTH_TOKEN = os.environ.get("SEI_AUTH_TOKEN", "test-token-change-me")
BIND_ADDR = os.environ.get("SEI_BIND", "127.0.0.1")
PORT = int(os.environ.get("SEI_PORT", "5052"))


async def process_request(connection, request):
    """Validate Bearer token before WebSocket upgrade."""
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {AUTH_TOKEN}":
        return connection.respond(HTTPStatus.UNAUTHORIZED, "Invalid token\n")


async def handler(websocket):
    """Echo messages back to the client."""
    print(f"Client connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            await websocket.send(f"echo: {message}")
    finally:
        print(f"Client disconnected: {websocket.remote_address}")


async def main():
    print(f"Echo server listening on {BIND_ADDR}:{PORT}")
    print(f"Auth: {'<from env>' if os.environ.get('SEI_AUTH_TOKEN') else 'test-token-change-me (DEFAULT)'}")
    async with serve(handler, BIND_ADDR, PORT, process_request=process_request) as server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEcho server stopped.")
