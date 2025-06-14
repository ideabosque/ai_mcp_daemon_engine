#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import functools
import os
import sys
import traceback
import zipfile
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    ImageContent,
    PromptMessage,
    TextContent,
)

from silvaengine_utility import Utility

from .config import Config

INSERT_UPDATE_MCP_FUNCTION_CALL = """mutation insertUpdateMcpFunctionCall(
    $arguments: JSON, 
    $content: String, 
    $mcpFunctionCallUuid: String, 
    $mcpType: String, 
    $name: String, 
    $notes: String, 
    $status: String, 
    $timeSpent: Int, 
    $updatedBy: String!
) {
    insertUpdateMcpFunctionCall(
        arguments: $arguments, 
        content: $content, 
        mcpFunctionCallUuid: $mcpFunctionCallUuid, 
        mcpType: $mcpType, 
        name: $name, 
        notes: $notes, 
        status: $status, 
        timeSpent: $timeSpent, 
        updatedBy: $updatedBy
    ) {
        mcpFunctionCall { 
            endpointId 
            mcpFunctionCallUuid 
            mcpType 
            name 
            arguments 
            content 
            status 
            notes 
            timeSpent 
            updatedBy 
            createdAt 
            updatedAt 
        }    
    }
}"""


def execute_decorator():
    def actual_decorator(original_function):
        @functools.wraps(original_function)
        def wrapper_function(*args, **kwargs):
            try:
                Config.logger.info("Starting execution of MCP function")
                mcp_function_call = None
                start_time = datetime.now()
                endpoint_id = args[0]
                if endpoint_id != "default":
                    Config.logger.info(f"Processing endpoint_id: {endpoint_id}")
                    mcp_type = original_function.__name__.replace(
                        "execute_", ""
                    ).replace("_function", "")
                    Config.logger.info(f"MCP type determined: {mcp_type}")

                    if mcp_type == "resource":
                        Config.logger.info("Processing resource type MCP")
                        resource = next(
                            (
                                resource
                                for resource in Config.fetch_mcp_configuration(
                                    endpoint_id
                                )["resources"]["resources"]
                                if resource["uri"] == args[1]
                            ),
                            None,
                        )
                        name = resource["name"]
                        arguments = {"uri": args[1]}
                        Config.logger.info(
                            f"Resource name: {name}, arguments: {arguments}"
                        )
                    else:
                        name = args[1]
                        arguments = args[2]
                        Config.logger.info(
                            f"Function name: {name}, arguments: {arguments}"
                        )

                    Config.logger.info(
                        "Making GraphQL call to insert/update MCP function"
                    )
                    response = Config.mcp_core.mcp_core_graphql(
                        **{
                            "endpoint_id": endpoint_id,
                            "query": INSERT_UPDATE_MCP_FUNCTION_CALL,
                            "variables": {
                                "name": name,
                                "mcpType": mcp_type,
                                "arguments": arguments,
                                "updatedBy": "mcp_daemon_engine",
                            },
                        }
                    )
                    response = Utility.json_loads(response)

                    if "errors" in response:
                        Config.logger.error(f"GraphQL error: {response['errors']}")
                        raise Exception(response["errors"])

                    mcp_function_call = response["data"]["insertUpdateMcpFunctionCall"][
                        "mcpFunctionCall"
                    ]
                    Config.logger.info("Successfully created MCP function call")

                Config.logger.info("Executing original function")
                result = original_function(*args, **kwargs)

                if mcp_function_call is not None:
                    end_time = datetime.now()
                    time_spent = int((end_time - start_time).total_seconds() * 1000)
                    Config.logger.info(f"Function execution time: {time_spent}ms")

                    Config.logger.info("Updating MCP function call with results")
                    response = Config.mcp_core.mcp_core_graphql(
                        **{
                            "endpoint_id": endpoint_id,
                            "query": INSERT_UPDATE_MCP_FUNCTION_CALL,
                            "variables": {
                                "mcpFunctionCallUuid": mcp_function_call[
                                    "mcpFunctionCallUuid"
                                ],
                                "content": result,
                                "status": "completed",
                                "timeSpent": time_spent,
                                "updatedBy": "mcp_daemon_engine",
                            },
                        }
                    )

                    if "errors" in response:
                        Config.logger.error(f"GraphQL error: {response['errors']}")
                        raise Exception(response["errors"])

                Config.logger.info("Successfully completed MCP function execution")
                return result

            except Exception as e:
                log = traceback.format_exc()
                Config.logger.error(f"Error in MCP function execution: {log}")
                if mcp_function_call is not None:
                    Config.logger.info("Updating MCP function call with error status")
                    response = Config.mcp_core.mcp_core_graphql(
                        **{
                            "endpoint_id": mcp_function_call["endpointId"],
                            "query": INSERT_UPDATE_MCP_FUNCTION_CALL,
                            "variables": {
                                "mcpFunctionCallUuid": mcp_function_call[
                                    "mcpFunctionCallUuid"
                                ],
                                "notes": log,
                                "status": "failed",
                                "updatedBy": "mcp_daemon_engine",
                            },
                        }
                    )
                raise e

        return wrapper_function

    return actual_decorator


def module_exists(module_name: str) -> bool:
    """Check if the module exists in the specified path."""
    module_dir = os.path.join(Config.funct_extract_path, module_name)
    if os.path.exists(module_dir) and os.path.isdir(module_dir):
        Config.logger.info(
            f"Module {module_name} found in {Config.funct_extract_path}."
        )
        return True
    Config.logger.info(
        f"Module {module_name} not found in {Config.funct_extract_path}."
    )
    return False


def download_and_extract_module(module_name: str) -> None:
    """Download and extract the module from S3 if not already extracted."""
    key = f"{module_name}.zip"
    zip_path = f"{Config.funct_zip_path}/{key}"

    Config.logger.info(
        f"Downloading module from S3: bucket={Config.funct_bucket_name}, key={key}"
    )
    Config.aws_s3.download_file(Config.funct_bucket_name, key, zip_path)
    Config.logger.info(f"Downloaded {key} from S3 to {zip_path}")

    # Extract the ZIP file
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(Config.funct_extract_path)
    Config.logger.info(f"Extracted module to {Config.funct_extract_path}")


def get_function(
    module_name: str, function_name: str, source=None
) -> Optional[Callable]:
    try:
        if source is None:
            return getattr(__import__(module_name), function_name)

        if not module_exists(module_name):
            # Download and extract the module if it doesn't exist
            download_and_extract_module(module_name)

        # Add the extracted module to sys.path
        module_path = f"{Config.funct_extract_path}/{module_name}"
        if module_path not in sys.path:
            sys.path.append(module_path)

        return getattr(__import__(module_name), function_name)

    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e


@execute_decorator()
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

        tool_function = get_function(
            tool_module["module_name"],
            tool_module["function_name"],
            source=tool_module.get("source"),
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


@execute_decorator()
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

        resource_function = get_function(
            resource_module["module_name"],
            resource_module["function_name"],
            source=resource_module.get("source"),
        )

        result = resource_function(Config.logger, resource_module["setting"], uri)
        return result

    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e


@execute_decorator()
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

        prompt_function = get_function(
            prompt_module["module_name"],
            prompt_module["function_name"],
            source=prompt_module.get("source"),
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
