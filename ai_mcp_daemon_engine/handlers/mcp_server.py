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
async def list_tools(endpoint_id: str = "default") -> List[Tool]:
    """List available tools for the given endpoint"""
    tools = Config.fetch_mcp_configuration(endpoint_id)["tools"]["tools"]
    return [Tool(**tool) for tool in tools]


@server.call_tool()
async def call_tool(
    name: str, arguments: Optional[Dict[str, Any]], endpoint_id: str = "default"
) -> List[Union[TextContent, ImageContent, EmbeddedResource]]:
    """Call a specific tool with given arguments"""
    tools = Config.fetch_mcp_configuration(endpoint_id)["tools"]["tools"]
    if not any(tool["name"] == name for tool in tools):
        raise ValueError(f"Unknown tool: {name}")

    return execute_tool_function(endpoint_id, name, arguments)


@server.list_resources()
async def list_resources(endpoint_id: str = "default") -> List[Resource]:
    """List available resources for the given endpoint"""
    resources = Config.fetch_mcp_configuration(endpoint_id)["resources"]["resources"]

    return [Resource(**resource) for resource in resources]


@server.read_resource()
async def read_resource(uri: str, endpoint_id: str = "default") -> str:
    """Read content of a specific resource"""
    resources = Config.fetch_mcp_configuration(endpoint_id)["resources"]["resources"]
    if not any(resource["uri"] == uri for resource in resources):
        raise ValueError(f"Unknown resource: {uri}")

    return execute_resource_function(endpoint_id, uri)


@server.list_prompts()
async def list_prompts(endpoint_id: str = "default") -> List[Prompt]:
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
    name: str, arguments: Optional[Dict[str, Any]], endpoint_id: str = "default"
) -> GetPromptResult:
    """Get a specific prompt with given arguments"""
    prompts = Config.fetch_mcp_configuration(endpoint_id)["prompts"]["prompts"]
    if not any(prompt["name"] == name for prompt in prompts):
        raise ValueError(f"Unknown prompt: {name}")

    return execute_prompt_function(endpoint_id, name, arguments)


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
