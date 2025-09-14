#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import asyncio
import concurrent.futures
import functools
import os
import sys
import threading
import traceback
import zipfile
from datetime import datetime
from typing import Any, Dict, Optional

from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    ImageContent,
    PromptMessage,
    ReadResourceResult,
    TextContent,
    TextResourceContents,
)

from silvaengine_utility import Utility

from .config import Config

# Global registry to track active background threads
_active_threads = []


def wait_for_background_threads(timeout=30):
    """Wait for all background threads to complete before shutdown."""
    if not _active_threads:
        return

    Config.logger.info(
        f"Waiting for {len(_active_threads)} background threads to complete..."
    )

    for thread in _active_threads[
        :
    ]:  # Copy list to avoid modification during iteration
        if thread.is_alive():
            Config.logger.info(
                f"Waiting for thread {thread.name if hasattr(thread, 'name') else 'unnamed'}..."
            )
            thread.join(timeout=timeout)
            if thread.is_alive():
                Config.logger.warning(
                    f"Thread {thread.name if hasattr(thread, 'name') else 'unnamed'} did not complete within {timeout}s"
                )

    _active_threads.clear()
    Config.logger.info("Background thread cleanup completed")


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


MCP_FUNCTION_CALL = """query mcpFunctionCall($mcpFunctionCallUuid: String!) {
    mcpFunctionCall(mcpFunctionCallUuid: $mcpFunctionCallUuid) {
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

                if kwargs.get("mcp_function_call_uuid"):
                    response = Config.mcp_core.mcp_core_graphql(
                        **{
                            "endpoint_id": endpoint_id,
                            "query": MCP_FUNCTION_CALL,
                            "variables": {
                                "mcpFunctionCallUuid": kwargs["mcp_function_call_uuid"],
                            },
                        }
                    )
                    response = Utility.json_loads(response)

                    if "errors" in response:
                        Config.logger.error(f"GraphQL error: {response['errors']}")
                        raise Exception(response["errors"])

                    mcp_function_call = response["data"]["mcpFunctionCall"]

                if endpoint_id != "default" and mcp_function_call is None:
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
                                )["resources"]
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

                content = None
                if isinstance(result, list):
                    content = []
                    for item in result:
                        if isinstance(item, EmbeddedResource):
                            content.append(item.model_dump())
                        elif isinstance(item, TextContent):
                            content.append(item.model_dump())
                        elif isinstance(item, ImageContent):
                            content.append(item.model_dump())
                        else:
                            content.append(item)
                elif isinstance(result, (ReadResourceResult, GetPromptResult)):
                    # Handle MCP structured result types
                    content = result.model_dump()
                else:
                    # Handle other types (strings, dicts, etc.)
                    content = result

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
                                "content": Utility.json_dumps(content),
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


def get_mcp_configuration_with_retry(
    endpoint_id: str, max_retries: int = 1
) -> Dict[str, Any]:
    """
    Get MCP configuration with automatic retry on failure.

    Args:
        endpoint_id: Endpoint ID to fetch configuration for
        max_retries: Maximum number of retry attempts with cache refresh

    Returns:
        MCP configuration dictionary

    Raises:
        Exception: If configuration cannot be retrieved after retries
    """
    for attempt in range(max_retries + 1):
        try:
            force_refresh = attempt > 0  # Force refresh on retry attempts
            return Config.fetch_mcp_configuration(
                endpoint_id, force_refresh=force_refresh
            )
        except Exception as e:
            if attempt < max_retries:
                Config.logger.warning(
                    f"Failed to fetch MCP config for {endpoint_id} (attempt {attempt + 1}), "
                    f"retrying with cache refresh: {e}"
                )
                # Clear cache before retry
                Config.clear_mcp_configuration_cache(endpoint_id)
                continue
            else:
                Config.logger.error(
                    f"Failed to fetch MCP config for {endpoint_id} after {max_retries + 1} attempts: {e}"
                )
                raise


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


def download_and_extract_package(package_name: str) -> None:
    """Download and extract the module from S3 if not already extracted."""
    key = f"{package_name}.zip"
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


def get_class(
    package_name: str, module_name: str, class_name: str, source: str = None
) -> Optional[type]:
    try:
        if source is None:
            return getattr(__import__(module_name), class_name)

        # Check if the module exists
        if not module_exists(module_name):
            # Download and extract the module if it doesn't exist
            download_and_extract_package(package_name)

        # Add the extracted module to sys.path
        module_path = f"{Config.funct_extract_path}/{module_name}"
        if module_path not in sys.path:
            sys.path.append(module_path)

        # Import the module and get the class
        module = __import__(module_name)
        return getattr(module, class_name)
    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e


def _validate_nested_structure(
    schema: Dict[str, Any], data: Dict[str, Any], field_path: str = ""
) -> None:
    """
    Private function to recursively validate required fields in nested objects and arrays.

    Args:
        schema: JSON schema definition for the data structure
        data: The actual data to validate
        field_path: Current field path for error reporting
    """
    import copy

    if schema.get("type") == "object" and "properties" in schema:
        # Handle object validation
        nested_required = schema.get("required", [])
        nested_properties = schema["properties"]

        for nested_key, nested_schema in nested_properties.items():
            nested_path = f"{field_path}.{nested_key}" if field_path else nested_key

            if nested_key not in data:
                if "default" in nested_schema:
                    default_value = nested_schema["default"]
                    if isinstance(default_value, (dict, list)):
                        data[nested_key] = copy.deepcopy(default_value)
                    else:
                        data[nested_key] = default_value
                elif nested_key in nested_required:
                    raise Exception(f"Missing required argument: {nested_path}")
            else:
                # Recursively validate nested structures
                _validate_nested_structure(nested_schema, data[nested_key], nested_path)

    elif schema.get("type") == "array" and "items" in schema:
        # Handle array validation
        items_schema = schema["items"]
        if isinstance(data, list):
            for i, item in enumerate(data):
                item_path = f"{field_path}[{i}]" if field_path else f"[{i}]"
                _validate_nested_structure(items_schema, item, item_path)


def _validate_and_set_defaults(
    tool_schema: Dict[str, Any], arguments: Dict[str, Any]
) -> None:
    """
    Private function to validate arguments and set default values based on tool schema.
    Handles nested objects and arrays with required field validation.
    """
    import copy

    if not tool_schema.get("inputSchema", {}).get("properties"):
        return

    schema_properties = tool_schema["inputSchema"]["properties"]
    required_fields = tool_schema["inputSchema"].get("required", [])

    # Handle top-level properties
    for key, schema in schema_properties.items():
        if key not in arguments:
            if "default" in schema:
                default_value = schema["default"]
                if isinstance(default_value, (dict, list)):
                    arguments[key] = copy.deepcopy(default_value)
                else:
                    arguments[key] = default_value
            elif key in required_fields:
                raise Exception(f"Missing required argument: {key}")
        else:
            # Validate provided arguments
            _validate_nested_structure(schema, arguments[key], key)


@execute_decorator()
def execute_tool_function(
    endpoint_id: str,
    name: str,
    arguments: Dict[str, Any],
    mcp_function_call_uuid: str = None,
) -> list[TextContent | ImageContent | EmbeddedResource]:
    try:
        config = get_mcp_configuration_with_retry(endpoint_id)
        tool = next(
            (tool for tool in config["tools"] if tool["name"] == name),
            {},
        )

        # Validate arguments and set defaults using the tool schema
        _validate_and_set_defaults(tool, arguments)

        module_link = next(
            (
                module_link
                for module_link in config["module_links"]
                if module_link["name"] == name and module_link["type"] == "tool"
            ),
            {},
        )

        module = next(
            (
                module
                for module in config["modules"]
                if (
                    module["module_name"] == module_link["module_name"]
                    and module["class_name"] == module_link["class_name"]
                )
            ),
            {},
        )

        tool_class = get_class(
            module["package_name"],
            module["module_name"],
            module["class_name"],
            source=module.get("source"),
        )

        tool_function = getattr(
            tool_class(
                Config.logger,
                **Utility.json_loads(Utility.json_dumps(module["setting"])),
            ),
            module_link["function_name"],
        )

        if "endpoint_id" not in arguments:
            arguments["endpoint_id"] = endpoint_id

        if module_link.get("is_async", False):
            if Config.aws_lambda:
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, tool_function(**arguments))
                    result = future.result()
            else:
                result = asyncio.run(tool_function(**arguments))
        else:
            result = tool_function(**arguments)

        return_type = module_link["return_type"]

        if return_type == "text":
            # Handle dict result by converting to JSON representation
            if isinstance(result, dict):
                return [TextContent(type="text", text=Utility.json_dumps(result))]
            return [TextContent(type="text", text=str(result))]

        elif return_type == "image":
            # Handle image results
            if isinstance(result, dict):
                # Expected format: {"data": "base64_data", "mimeType": "image/png"}
                return [
                    ImageContent(
                        type="image",
                        data=result.get("data", ""),
                        mimeType=result.get("mimeType", "image/png"),
                    )
                ]
            elif isinstance(result, str):
                # Assume base64 encoded PNG if just string
                return [ImageContent(type="image", data=result, mimeType="image/png")]
            else:
                raise Exception(f"Invalid image result format: {type(result)}")

        elif return_type == "embedded_resource":
            return _create_embedded_resource_from_result(result)

        else:
            raise Exception(
                f"Invalid return type {return_type}. Supported types: text, image, resource"
            )

    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e


def _create_embedded_resource_from_result(result) -> list[EmbeddedResource]:
    """Convert function result to EmbeddedResource with proper TextResourceContents."""
    # Extract resource data and determine content
    resource_data = (
        result.get("resource", result) if isinstance(result, dict) else result
    )

    if isinstance(resource_data, dict) and "text" in resource_data:
        # Use existing text content
        text_content = str(resource_data["text"])
        mime_type = resource_data.get("mimeType")

        # Auto-detect JSON if no mimeType provided
        if not mime_type:
            try:
                Utility.json_loads(text_content)
                mime_type = "application/json"
            except:
                mime_type = "text/plain"
    else:
        # Convert to JSON string (for dicts) or plain string
        if isinstance(resource_data, dict):
            text_content = Utility.json_dumps(resource_data)
            mime_type = resource_data.get("mimeType", "application/json")
        else:
            text_content = str(resource_data)
            mime_type = "text/plain"

    return [
        EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                text=text_content, mimeType=mime_type or "text/plain"
            ),
        )
    ]


@execute_decorator()
def execute_resource_function(
    endpoint_id: str,
    uri: str,
) -> ReadResourceResult:
    try:
        config = get_mcp_configuration_with_retry(endpoint_id)
        resource = next(
            (resource for resource in config["resources"] if resource["uri"] == uri),
            {},
        )

        module_link = next(
            (
                module_link
                for module_link in config["module_links"]
                if module_link["name"] == resource["name"]
                and module_link["type"] == "resource"
            ),
            {},
        )

        module = next(
            (
                module
                for module in config["modules"]
                if (
                    module["module_name"] == module_link["module_name"]
                    and module["class_name"] == module_link["class_name"]
                )
            ),
            {},
        )

        resource_class = get_class(
            module["package_name"],
            module["module_name"],
            module["class_name"],
            source=module.get("source"),
        )

        resource_function = getattr(
            resource_class(
                Config.logger,
                **Utility.json_loads(Utility.json_dumps(module["setting"])),
            ),
            module_link["function_name"],
        )

        result = resource_function(uri)

        # Return properly structured ReadResourceResult according to MCP specification
        return ReadResourceResult(
            contents=[
                TextResourceContents(uri=uri, mimeType="text/plain", text=str(result))
            ]
        )

    except Exception as e:
        log = traceback.format_exc()
        Config.logger.error(log)
        raise e


@execute_decorator()
def execute_prompt_function(
    endpoint_id: str,
    name: str,
    arguments: Dict[str, Any],
) -> GetPromptResult:
    try:
        config = get_mcp_configuration_with_retry(endpoint_id)
        prompt = next(
            (prompt for prompt in config["prompts"] if prompt["name"] == name),
            {},
        )

        # Check if arguments have all required arguments
        if prompt.get("arguments"):
            for arg in prompt["arguments"]:
                if arg.get("required", False) and arg["name"] not in arguments.keys():
                    raise Exception(f"Missing required argument {arg['name']}")

        module_link = next(
            (
                module_link
                for module_link in config["module_links"]
                if module_link["name"] == name and module_link["type"] == "prompt"
            ),
            {},
        )

        module = next(
            (
                module
                for module in config["modules"]
                if (
                    module["module_name"] == module_link["module_name"]
                    and module["class_name"] == module_link["class_name"]
                )
            ),
            {},
        )

        prompt_class = get_class(
            module["package_name"],
            module["module_name"],
            module["class_name"],
            source=module.get("source"),
        )

        prompt_function = getattr(
            prompt_class(
                Config.logger,
                **Utility.json_loads(Utility.json_dumps(module["setting"])),
            ),
            module_link["function_name"],
        )

        if "endpoint_id" not in arguments:
            arguments["endpoint_id"] = endpoint_id

        result = prompt_function(name, **arguments)

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


def async_execute_tool_function(
    endpoint_id: str,
    name: str,
    arguments: Dict[str, Any],
):
    if arguments.get("mcp_function_call_uuid"):
        response = Config.mcp_core.mcp_core_graphql(
            **{
                "endpoint_id": endpoint_id,
                "query": MCP_FUNCTION_CALL,
                "variables": {
                    "mcpFunctionCallUuid": arguments["mcp_function_call_uuid"],
                },
            }
        )
        response = Utility.json_loads(response)

        if "errors" in response:
            Config.logger.error(f"GraphQL error: {response['errors']}")
            raise Exception(response["errors"])

        mcp_function_call = response["data"]["mcpFunctionCall"]

        return [TextContent(type="text", text=mcp_function_call["content"])]

    Config.logger.info("Making GraphQL call to insert/update MCP function")
    response = Config.mcp_core.mcp_core_graphql(
        **{
            "endpoint_id": endpoint_id,
            "query": INSERT_UPDATE_MCP_FUNCTION_CALL,
            "variables": {
                "name": name,
                "mcpType": "tool",
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

    params = {
        "name": name,
        "arguments": arguments,
        "mcp_function_call_uuid": mcp_function_call["mcpFunctionCallUuid"],
    }

    if Config.aws_lambda:
        # Invoke Lambda function asynchronously
        Config.logger.info("Invoking Lambda function asynchronously")
        Utility.invoke_funct_on_aws_lambda(
            Config.logger,
            endpoint_id,
            "async_execute_tool_function",
            params=params,
            setting=Config.setting,
            test_mode=Config.setting.get("test_mode"),
            aws_lambda=Config.aws_lambda,
            invocation_type="Event",
        )
    else:
        Config.logger.info("Dispatching execute_tool_function in a separate thread")
        thread = threading.Thread(
            target=execute_tool_function,
            args=(
                endpoint_id,
                name,
                arguments,
            ),
            kwargs={"mcp_function_call_uuid": mcp_function_call["mcpFunctionCallUuid"]},
            daemon=False,  # Changed to False so thread won't be killed when main process exits
        )
        thread.start()

        # Register thread for tracking
        _active_threads.append(thread)
        Config.logger.info(
            f"Tool function {name} started in background thread (active threads: {len(_active_threads)})"
        )

        # Clean up completed threads
        _active_threads[:] = [t for t in _active_threads if t.is_alive()]

    return [
        EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                uri=f"mcp://function-call/{mcp_function_call['mcpFunctionCallUuid']}",
                text=Utility.json_dumps(
                    {"mcp_function_call_uuid": mcp_function_call["mcpFunctionCallUuid"]}
                ),
                mimeType="application/json",
            ),
        )
    ]
