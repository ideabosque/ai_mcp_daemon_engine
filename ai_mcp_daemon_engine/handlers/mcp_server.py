#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "bibow"

import logging
import sys
from typing import Any, Dict, List, Optional, Union

from fastapi.encoders import jsonable_encoder
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

from .config import Config
from .mcp_utility import (
    execute_prompt_function,
    execute_resource_function,
    execute_tool_function,
)

# === FastAPI and MCP Initialization ===
server = Server("MCP SSE Server")


# === Tool Definitions ===
@server.list_tools()
async def list_tools(endpoint_id: str) -> List[Tool]:
    """List available tools for the given endpoint"""
    tools = Config.fetch_mcp_configuration(endpoint_id)["tools"]["tools"]
    return [Tool(**tool) for tool in tools]


@server.call_tool()
async def call_tool(
    endpoint_id: str, name: str, arguments: Optional[Dict[str, Any]]
) -> List[Union[TextContent, ImageContent, EmbeddedResource]]:
    """Call a specific tool with given arguments"""
    tools = Config.fetch_mcp_configuration(endpoint_id)["tools"]["tools"]
    if not any(tool["name"] == name for tool in tools):
        raise ValueError(f"Unknown tool: {name}")

    return execute_tool_function(endpoint_id, name, arguments)


@server.list_resources()
async def list_resources(endpoint_id: str) -> List[Resource]:
    """List available resources for the given endpoint"""
    resources = Config.fetch_mcp_configuration(endpoint_id)["resources"]["resources"]

    return [Resource(**resource) for resource in resources]


@server.read_resource()
async def read_resource(endpoint_id: str, uri: str) -> str:
    """Read content of a specific resource"""
    resources = Config.fetch_mcp_configuration(endpoint_id)["resources"]["resources"]
    if not any(resource["uri"] == uri for resource in resources):
        raise ValueError(f"Unknown resource: {uri}")

    return execute_resource_function(endpoint_id, uri)


@server.list_prompts()
async def list_prompts(endpoint_id: str) -> List[Prompt]:
    """List available prompts for the given endpoint"""
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
    endpoint_id: str, name: str, arguments: Optional[Dict[str, str]]
) -> GetPromptResult:
    """Get a specific prompt with given arguments"""
    prompts = Config.fetch_mcp_configuration(endpoint_id)["prompts"]["prompts"]
    if not any(prompt["name"] == name for prompt in prompts):
        raise ValueError(f"Unknown prompt: {name}")

    return execute_prompt_function(endpoint_id, name, arguments)


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


async def run_stdio(logger: logging.Logger) -> None:
    """Run MCP server with stdio transport"""
    logger.info("Starting MCP Server with stdio transport...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Stdio server error: {e}")
        sys.exit(1)
