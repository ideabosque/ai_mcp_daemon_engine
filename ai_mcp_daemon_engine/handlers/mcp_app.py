#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "bibow"

import asyncio
import json
from collections import deque
from datetime import datetime
from itertools import count
from typing import Any, AsyncGenerator, Dict

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from silvaengine_utility import Utility

from .config import Config
from .mcp_server import (
    call_tool,
    get_prompt,
    list_prompts,
    list_resources,
    list_tools,
    read_resource,
)

# === SSE State ===
client_id_seq = count(1)  # atomic client‑id generator
message_id_seq = count(1)  # atomic message‑id generator
message_history: deque[dict] = deque(maxlen=1000)  # replay buffer

# === FastAPI and MCP Initialization ===
app = FastAPI(title="MCP SSE Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === MCP Message Handling ===
async def process_mcp_message(endpoint_id: str, message: Dict) -> Dict:
    """Process incoming MCP messages"""
    try:
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": {"name": "SSE Server", "version": "1.0.0"},
                },
            }

        elif method == "tools/list":
            tools = await list_tools(endpoint_id=endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": jsonable_encoder(tools)},
            }

        elif method == "tools/call":
            result = await call_tool(
                params["name"], params.get("arguments"), endpoint_id=endpoint_id
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": jsonable_encoder(result)},
            }

        elif method == "resources/list":
            resources = await list_resources(endpoint_id=endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resources": jsonable_encoder(resources)},
            }

        elif method == "resources/read":
            content = await read_resource(params["uri"], endpoint_id=endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "contents": [
                        {
                            "uri": params["uri"],
                            "mimeType": "text/plain",
                            "text": content,
                        }
                    ]
                },
            }

        # Handle MCP protocol messages
        elif method == "prompts/list":
            # Handle list prompts request
            prompts = await list_prompts(endpoint_id=endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "prompts": [
                        {
                            "name": prompt.name,
                            "description": prompt.description,
                            "arguments": [
                                {
                                    "name": arg.name,
                                    "description": arg.description,
                                    "required": arg.required,
                                }
                                for arg in (prompt.arguments or [])
                            ],
                        }
                        for prompt in prompts
                    ]
                },
            }

        elif method == "prompts/get":
            # Handle get prompt request
            result = await get_prompt(
                params["name"], params.get("arguments"), endpoint_id=endpoint_id
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "description": result.description,
                    "messages": [
                        {
                            "role": msg.role,
                            "content": {
                                "type": msg.content.type,
                                "text": msg.content.text,
                            },
                        }
                        for msg in result.messages
                    ],
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32603, "message": "Internal error", "data": str(e)},
        }


# === SSE Event Generator ===
async def sse_event_generator(
    request: Request, client_id: int, username: str, queue: asyncio.Queue
) -> AsyncGenerator[str, None]:
    """Generate SSE events for connected clients"""
    yield f"event: connected\ndata: {json.dumps({'client_id': client_id, 'timestamp': datetime.now().isoformat()})}\n\n"
    try:
        while not await request.is_disconnected():
            try:
                message = await asyncio.wait_for(queue.get(), timeout=15)
                yield f"data: {json.dumps(jsonable_encoder(message))}\n\n"
            except asyncio.TimeoutError:
                yield f"event: heartbeat\ndata: {json.dumps({'client_id': client_id, 'timestamp': datetime.now().isoformat()})}\n\n"
    finally:
        Config.sse_clients.pop(client_id, None)
        cids = Config.user_clients.get(username, set())
        cids.discard(client_id)
        if not cids:
            Config.user_clients.pop(username, None)


# === Broadcast Logic ===
async def broadcast_to_clients(message: Dict) -> None:
    """Send an event to all connected clients and record it for replay"""
    message_id = next(message_id_seq)
    message_with_id = dict(message, id=message_id)
    message_history.append(message_with_id)

    dead_clients = []
    for client_id, queue in list(Config.sse_clients.items()):
        try:
            await queue.put(message_with_id)
        except asyncio.QueueFull:
            dead_clients.append(client_id)
    for cid in dead_clients:
        Config.sse_clients.pop(cid, None)


async def send_to_client(cid: int, message: Dict[str, Any]) -> bool:
    """Unicast a message to one client, with id-stamping & replay tracking"""
    message_id = next(message_id_seq)
    message_with_id = dict(message, id=message_id)
    message_history.append(message_with_id)

    q = Config.sse_clients.get(cid)
    if not q:
        return False
    try:
        q.put_nowait(message_with_id)
        return True
    except asyncio.QueueFull:
        Config.sse_clients.pop(cid, None)
        Config.logger.warning("Queue full – evict client %s", cid)
        return False


async def send_to_user(username: str, message: dict[str, Any]) -> bool:
    """Send a message to *all* live connections for a user."""
    cids = Config.user_clients.get(username)
    if not cids:
        return False
    delivered = False
    for cid in set(cids):  # copy to avoid set-size change
        ok = await send_to_client(cid, message)
        delivered = delivered or ok
    return delivered


def current_user(request: Request) -> Dict:
    """Get current authenticated user"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@app.get("/me")
def me(user: Dict = Depends(current_user)) -> Dict:
    """Get current user info"""
    return user


# === GET /sse Endpoint ===
@app.get("/{endpoint_id}/sse")
async def get_sse_stream(
    endpoint_id: str,
    request: Request,
    user: Dict = Depends(current_user),
    origin: str = Header(None),
) -> StreamingResponse:
    """Handle SSE stream connections"""
    # Validate Origin header to prevent DNS rebinding attacks
    # if origin != "http://your-allowed-origin.com":  # Replace with your allowed origin
    #     raise HTTPException(status_code=403, detail="Forbidden")

    client_id = next(client_id_seq)
    queue = asyncio.Queue(maxsize=100)
    last_event_id = request.headers.get("last-event-id")
    if last_event_id and last_event_id.isdigit():
        missed = [m for m in message_history if m["id"] > int(last_event_id)]
        for m in missed:
            await queue.put(m)
    Config.sse_clients[client_id] = queue
    Config.user_clients.setdefault(user["username"], set()).add(client_id)

    metadata = {
        "type": "mcp_activity",
        "method": "initialize",
        "response": {
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": "MCP SSE Server", "version": "1.0.0"},
            }
        },
    }
    await queue.put(metadata)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        sse_event_generator(request, client_id, user["username"], queue),
        media_type="text/event-stream",
        headers=headers,
    )


@app.post("/{endpoint_id}/mcp")
async def post_mcp_message(
    endpoint_id: str, request: Request, user: Dict = Depends(current_user)
) -> Dict:
    """Handle MCP protocol messages"""
    try:
        message = await request.json()
        response = await process_mcp_message(endpoint_id, message)
        await send_to_user(
            user["username"],
            {
                "type": "mcp_activity",
                "method": message["method"],
                "request": jsonable_encoder(message),
                "response": jsonable_encoder(response),
                "timestamp": datetime.now().isoformat(),
            },
        )
        return response
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32603, "message": "Internal error", "data": str(e)},
        }


# === Diagnostics ===
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Check server health status"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "sse_clients": len(Config.sse_clients),
    }


@app.get("/{endpoint_id}")
async def root(endpoint_id: str) -> Dict[str, Any]:
    """Get endpoint info including tools, resources and prompts"""
    tools = await list_tools(endpoint_id)
    resources = await list_resources(endpoint_id)
    prompts = await list_prompts(endpoint_id)
    return {
        "server": "MCP SSE Server",
        "version": "1.0.0",
        "connected_clients": len(Config.sse_clients),
        "tools": jsonable_encoder(tools),
        "resources": jsonable_encoder(resources),
        "prompts": jsonable_encoder(prompts),
    }


# === GraphQL Endpoint ===
@app.post("/{endpoint_id}/mcp_core_graphql")
async def mcp_core_graphql(endpoint_id: str, request: Request) -> Dict:
    """Handle GraphQL queries"""
    params = await request.json()
    params.update({"endpoint_id": endpoint_id})

    return Utility.json_loads(Config.mcp_core.mcp_core_graphql(**params))
