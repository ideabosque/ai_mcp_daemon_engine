#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "bibow"

import logging
import sys
from typing import Any, Dict, List, Optional, Union

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
    async_execute_tool_function,
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
    from .mcp_utility import get_mcp_configuration_with_retry

    config = get_mcp_configuration_with_retry(endpoint_id)
    tools = config["tools"]
    return [Tool(**tool) for tool in tools]


@server.call_tool()
async def call_tool(
    name: str, arguments: Optional[Dict[str, Any]], endpoint_id: str = "default"
) -> List[Union[TextContent, ImageContent, EmbeddedResource]]:
    """Call a specific tool with given arguments"""
    from .mcp_utility import get_mcp_configuration_with_retry

    config = get_mcp_configuration_with_retry(endpoint_id)
    tools = config["tools"]
    if not any(tool["name"] == name for tool in tools):
        raise ValueError(f"Unknown tool: {name}")

    module_link = next(
        (
            module_link
            for module_link in config["module_links"]
            if module_link["name"] == name and module_link["type"] == "tool"
        ),
        {},
    )
    if module_link.get("is_async", False):
        if endpoint_id == "default":
            raise ValueError(
                "Async tools are not supported with default endpoint_id - please provide a specific endpoint_id"
            )
        return async_execute_tool_function(endpoint_id, name, arguments)

    return execute_tool_function(endpoint_id, name, arguments)


@server.list_resources()
async def list_resources(endpoint_id: str = "default") -> List[Resource]:
    """List available resources for the given endpoint"""
    from .mcp_utility import get_mcp_configuration_with_retry

    config = get_mcp_configuration_with_retry(endpoint_id)
    resources = config["resources"]

    return [Resource(**resource) for resource in resources]


@server.read_resource()
async def read_resource(uri: str, endpoint_id: str = "default") -> str:
    """Read content of a specific resource"""
    from .mcp_utility import get_mcp_configuration_with_retry

    config = get_mcp_configuration_with_retry(endpoint_id)
    resources = config["resources"]
    if not any(resource["uri"] == uri for resource in resources):
        raise ValueError(f"Unknown resource: {uri}")

    return execute_resource_function(endpoint_id, uri)


@server.list_prompts()
async def list_prompts(endpoint_id: str = "default") -> List[Prompt]:
    """List available prompts for the given endpoint"""
    from .mcp_utility import get_mcp_configuration_with_retry

    config = get_mcp_configuration_with_retry(endpoint_id)
    prompts = config["prompts"]

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
    from .mcp_utility import get_mcp_configuration_with_retry

    config = get_mcp_configuration_with_retry(endpoint_id)
    prompts = config["prompts"]
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
            tools = await list_tools(endpoint_id=endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema,
                        }
                        for tool in tools
                    ]
                },
            }

        elif method == "tools/call":
            result = await call_tool(
                params["name"], params.get("arguments"), endpoint_id=endpoint_id
            )
            # Convert content objects to dictionaries for JSON serialization
            serialized_content = []
            for item in result:
                if hasattr(item, "model_dump"):
                    # Use Pydantic model serialization if available with JSON mode for proper URL serialization
                    serialized_content.append(item.model_dump(mode="json"))
                else:
                    # Manual serialization for TextContent, ImageContent, etc.
                    content_dict = {
                        "type": item.type,
                    }
                    if hasattr(item, "text"):
                        content_dict["text"] = item.text
                    if hasattr(item, "data"):
                        content_dict["data"] = item.data
                    if hasattr(item, "mimeType"):
                        content_dict["mimeType"] = item.mimeType
                    if hasattr(item, "name"):
                        content_dict["name"] = item.name
                    if hasattr(item, "uri"):
                        content_dict["uri"] = item.uri
                    if hasattr(item, "resource"):
                        if hasattr(item.resource, "model_dump"):
                            content_dict["resource"] = item.resource.model_dump(
                                mode="json"
                            )
                        else:
                            content_dict["resource"] = item.resource
                    # Add _meta field as empty object if not present
                    content_dict["_meta"] = getattr(item, "_meta", {})
                    serialized_content.append(content_dict)

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": serialized_content},
            }

        elif method == "resources/list":
            resources = await list_resources(endpoint_id=endpoint_id)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "resources": [
                        {
                            "uri": str(resource.uri),
                            "name": resource.name,
                            "description": resource.description,
                            "mimeType": resource.mimeType,
                        }
                        for resource in resources
                    ]
                },
            }

        elif method == "resources/templates/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resourceTemplates": []},
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
                            "_meta": {},
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
            # Serialize messages with proper content serialization
            serialized_messages = []
            for msg in result.messages:
                # Serialize the content object properly
                if hasattr(msg.content, "model_dump"):
                    content_dict = msg.content.model_dump()
                else:
                    content_dict = {
                        "type": msg.content.type,
                        "text": msg.content.text,
                        "_meta": getattr(msg.content, "_meta", {}),
                    }

                serialized_messages.append(
                    {
                        "role": msg.role,
                        "content": content_dict,
                    }
                )

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "description": result.description,
                    "messages": serialized_messages,
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
