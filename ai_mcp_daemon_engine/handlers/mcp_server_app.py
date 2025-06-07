#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "bibow"

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    ImageContent,
    Prompt,
    PromptArgument,
    Resource,
    TextContent,
    Tool,
)

from silvaengine_utility import Utility

from .config import Config
from .mcp_utility import (
    execute_prompt_function,
    execute_resource_function,
    execute_tool_function,
)

# === FastAPI and MCP Initialization ===
server = Server("MCP SSE Server")
app = FastAPI(title="MCP SSE Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Tool Definitions ===
@server.list_tools()
async def list_tools(endpoint_id: str) -> list[Tool]:
    tools = Config.fetch_mcp_configuration(endpoint_id)["tools"]["tools"]
    return [Tool(**tool) for tool in tools]


@server.call_tool()
async def call_tool(
    endpoint_id: str, name: str, arguments: dict[str, Any] | None
) -> list[TextContent | ImageContent | EmbeddedResource]:
    tools = Config.fetch_mcp_configuration(endpoint_id)["tools"]["tools"]
    if not any(tool["name"] == name for tool in tools):
        raise ValueError(f"Unknown tool: {name}")

    return execute_tool_function(endpoint_id, name, arguments)


@server.list_resources()
async def list_resources(endpoint_id: str) -> list[Resource]:
    resources = Config.fetch_mcp_configuration(endpoint_id)["resources"]["resources"]

    return [Resource(**resource) for resource in resources]


@server.read_resource()
async def read_resource(endpoint_id: str, uri: str) -> str:
    resources = Config.fetch_mcp_configuration(endpoint_id)["resources"]["resources"]
    if not any(resource["uri"] == uri for resource in resources):
        raise ValueError(f"Unknown resource: {uri}")

    return execute_resource_function(endpoint_id, uri)


@server.list_prompts()
async def list_prompts(endpoint_id: str) -> list[Prompt]:
    prompts = Config.fetch_mcp_configuration(endpoint_id)["prompts"]["prompts"]

    return [
        Prompt(
            name=prompt["name"],
            description=prompt["description"],
            arguments=[PromptArgument(**argument) for argument in prompt["arguments"]],
        )
        for prompt in prompts
    ]


@server.get_prompt()
async def get_prompt(
    endpoint_id: str, name: str, arguments: dict[str, str] | None
) -> GetPromptResult:
    prompts = Config.fetch_mcp_configuration(endpoint_id)["prompts"]["prompts"]
    if not any(prompt["name"] == name for prompt in prompts):
        raise ValueError(f"Unknown prompt: {name}")

    return execute_prompt_function(endpoint_id, name, arguments)


# === MCP Message Handling ===
async def process_stream_message(endpoint_id: str, message: dict) -> dict:
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
            tools = await list_tools(endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": jsonable_encoder(tools)},
            }

        elif method == "tools/call":
            result = await call_tool(
                endpoint_id, params["name"], params.get("arguments")
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": jsonable_encoder(result)},
            }

        elif method == "resources/list":
            resources = await list_resources(endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resources": jsonable_encoder(resources)},
            }

        elif method == "resources/read":
            content = await read_resource(endpoint_id, params["uri"])
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
            prompts = await list_prompts(endpoint_id)
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
                endpoint_id, params["name"], params.get("arguments")
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
    request: Request, client_id: int, queue: asyncio.Queue
) -> AsyncGenerator[str, None]:
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


# === GET /sse Endpoint ===
@app.get("/{endpoint_id}/sse")
async def get_sse_stream(
    endpoint_id: str, request: Request, origin: str = Header(None)
):
    # Validate Origin header to prevent DNS rebinding attacks
    # if origin != "http://your-allowed-origin.com":  # Replace with your allowed origin
    #     raise HTTPException(status_code=403, detail="Forbidden")

    Config.client_id_counter += 1
    client_id = Config.client_id_counter
    queue = asyncio.Queue(maxsize=100)
    Config.sse_clients[client_id] = queue

    # Send initial protocol metadata
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

    return StreamingResponse(
        sse_event_generator(request, client_id, queue), media_type="text/event-stream"
    )


# === POST /sse Endpoint ===
@app.post("/{endpoint_id}/sse")
async def post_sse_message(endpoint_id: str, request: Request):
    return await post_stream_message(endpoint_id, request)


# === MCP Endpoint ===
@app.post("/{endpoint_id}/mcp")
async def post_mcp_message(endpoint_id: str, request: Request):
    return await post_stream_message(endpoint_id, request)


async def post_stream_message(endpoint_id: str, request: Request):
    try:
        message = await request.json()
        response = await process_stream_message(endpoint_id, message)
        # if message.get("method") in {"tools/call", "resources/read", "prompts/get"}:
        await broadcast_to_clients(
            {
                "type": "mcp_activity",
                "method": message["method"],
                "request": jsonable_encoder(message),
                "response": jsonable_encoder(response),
                "timestamp": datetime.now().isoformat(),
            }
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
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "sse_clients": len(Config.sse_clients),
    }


@app.get("/{endpoint_id}")
async def root(endpoint_id: str) -> Dict[str, Any]:
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
async def mcp_core_graphql(endpoint_id: str, request: Request):
    params = await request.json()
    params.update({"endpoint_id": endpoint_id})

    return Utility.json_loads(Config.mcp_core_engine.mcp_core_graphql(**params))


# === Broadcast Logic ===
async def broadcast_to_clients(message: dict):
    for client_id, queue in list(Config.sse_clients.items()):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            Config.sse_clients.pop(client_id, None)


async def run_stdio(logger: logging.Logger):
    """Run MCP server with stdio transport"""
    logger.info("Starting MCP Server with stdio transport...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await Config.server.run(
                read_stream, write_stream, Config.server.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Stdio server error: {e}")
        sys.exit(1)
