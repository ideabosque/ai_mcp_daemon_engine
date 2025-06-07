#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import logging
import traceback
from typing import Any, Dict, List

from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    ImageContent,
    PromptMessage,
    TextContent,
)

from .config import Config


def execute_tool_function(
    endpoint_id: str,
    name: str,
    arguments: Dict[str, Any],
) -> list[TextContent | ImageContent | EmbeddedResource]:
    try:
        tool = next(
            (
                tool
                for tool in Config.fetch_mcp_configuration(endpoint_id)["tools"][
                    "tools"
                ]
                if tool["name"] == name
            ),
            {},
        )

        # Check if arguments have all required properties from input schema
        if tool.get("inputSchema", {}).get("properties"):
            for key in tool["inputSchema"]["properties"].keys():
                if key not in arguments.keys():
                    raise Exception(f"Missing argument {key}")

        tool_module = next(
            (
                tool_module
                for tool_module in Config.fetch_mcp_configuration(endpoint_id)["tools"][
                    "tool_modules"
                ]
                if tool_module["name"] == name
            ),
            {},
        )

        tool_function = getattr(
            __import__(tool_module["module_name"]), tool_module["function_name"]
        )
        result = tool_function(Config.logger, tool_module["setting"], **arguments)
        if tool_module["return_type"] == "text":
            return [TextContent(type="text", text=result)]
        else:
            raise Exception(f"Invalid return type {tool_module['return_type']}")

    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e


def execute_resource_function(
    endpoint_id: str,
    uri: str,
) -> str:
    try:
        resource = next(
            (
                resource
                for resource in Config.fetch_mcp_configuration(endpoint_id)[
                    "resources"
                ]["resources"]
                if resource["uri"] == uri
            ),
            {},
        )

        resource_module = next(
            (
                resource_module
                for resource_module in Config.fetch_mcp_configuration(endpoint_id)[
                    "resources"
                ]["resource_modules"]
                if resource_module["name"] == resource["name"]
            ),
            {},
        )

        resource_function = getattr(
            __import__(resource_module["module_name"]), resource_module["function_name"]
        )
        result = resource_function(Config.logger, resource_module["setting"], uri)
        return result

    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e


def execute_prompt_function(
    endpoint_id: str,
    name: str,
    arguments: Dict[str, Any],
) -> list[TextContent | ImageContent | EmbeddedResource]:
    try:
        prompt = next(
            (
                prompt
                for prompt in Config.fetch_mcp_configuration(endpoint_id)["prompts"][
                    "prompts"
                ]
                if prompt["name"] == name
            ),
            {},
        )

        # Check if arguments have all required arguments
        if prompt.get("arguments"):
            for arg in prompt["arguments"]:
                if arg.get("required", False) and arg["name"] not in arguments.keys():
                    raise Exception(f"Missing required argument {arg['name']}")

        prompt_module = next(
            (
                prompt_module
                for prompt_module in Config.fetch_mcp_configuration(endpoint_id)[
                    "prompts"
                ]["prompt_modules"]
                if prompt_module["name"] == name
            ),
            {},
        )

        prompt_function = getattr(
            __import__(prompt_module["module_name"]), prompt_module["function_name"]
        )
        result = prompt_function(
            Config.logger, prompt_module["setting"], name, **arguments
        )

        return GetPromptResult(
            description=prompt["description"],
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=result),
                )
            ],
        )

    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e
