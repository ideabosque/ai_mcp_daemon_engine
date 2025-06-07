# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import asyncio
import logging
from typing import Any, Dict

from silvaengine_utility import Utility

from ..models import utils
from .mcp_core_engine import MCPCoreEngine

MCP_FUNCTION_LIST = """query mcpFunctionList(
    $pageNumber: Int, 
    $limit: Int, 
    $mcpType: String, 
    $moduleName: String, 
    $functionName: String
) {
    mcpFunctionList(
        pageNumber: $pageNumber, 
        limit: $limit, 
        mcpType: $mcpType, 
        moduleName: $moduleName, 
        functionName: $functionName
    ) {
        pageSize 
        pageNumber 
        total 
        mcpFunctionList { 
            endpointId 
            name 
            mcpType 
            description 
            data 
            annotations 
            moduleName 
            functionName 
            setting 
            source 
            updatedBy 
            createdAt 
            updatedAt 
        }
    }
}"""


class Config:
    """
    Centralized Configuration Class
    Manages shared configuration variables across the application.
    """

    # === SSE Client Registry ===
    sse_clients: Dict[int, asyncio.Queue] = None
    client_id_counter = None
    transport = None
    port = None
    mcp_configuration = {}
    logger = None
    mcp_core_engine = None

    @classmethod
    def initialize(cls, logger: logging.Logger, **setting: Dict[str, Any]) -> None:
        """
        Initialize configuration setting.
        Args:
            logger (logging.Logger): Logger instance for logging.
            **setting (Dict[str, Any]): Configuration dictionary.
        """
        try:
            cls.logger = logger
            cls._set_parameters(setting)
            cls._initialize_mcp_core_engine(logger, setting)
            if setting.get("test_mode") == "local_for_all":
                cls._initialize_tables(logger)
            logger.info("Configuration initialized successfully.")
        except Exception as e:
            logger.exception("Failed to initialize configuration.")
            raise e

    @classmethod
    def _set_parameters(cls, setting: Dict[str, Any]) -> None:
        """
        Set application-level parameters.
        Args:
            setting (Dict[str, Any]): Configuration dictionary.
        """
        cls.sse_clients = {}
        cls.client_id_counter = 0
        cls.transport = setting["transport"]
        cls.port = setting["port"]
        if setting["mcp_configuration"] is not None:
            cls.logger.info("MCP Configuration loaded successfully.")
            cls.mcp_configuration["default"] = setting["mcp_configuration"]

    @classmethod
    def _initialize_mcp_core_engine(
        cls, logger: logging.Logger, setting: Dict[str, Any]
    ) -> None:
        """
        Initialize AWS services, such as the S3 client.
        Args:
            setting (Dict[str, Any]): Configuration dictionary.
        """
        if all(
            setting.get(k)
            for k in ["region_name", "aws_access_key_id", "aws_secret_access_key"]
        ):
            cls.mcp_core_engine = MCPCoreEngine(logger, **setting)

    @classmethod
    def _initialize_tables(cls, logger: logging.Logger) -> None:
        """
        Initialize database tables by calling the utils._initialize_tables() method.
        This is an internal method used during configuration setup.
        """
        utils._initialize_tables(logger)

    # Fetches and caches GraphQL schema for a given function
    @classmethod
    def fetch_mcp_configuration(
        cls,
        endpoint_id: str,
    ) -> Dict[str, Any]:
        """
        Fetches and caches a GraphQL schema for a given function.

        Args:
            logger: Logger instance for error reporting
            endpoint_id: ID of the endpoint to fetch schema from
            function_name: Name of function to get schema for
            setting: Optional settings dictionary

        Returns:
            Dict containing the GraphQL schema
        """
        # Check if schema exists in cache, if not fetch and store it
        if cls.mcp_configuration.get(endpoint_id) is None:
            response = cls.mcp_core_engine.mcp_core_graphql(
                **{
                    "endpoint_id": endpoint_id,
                    "query": MCP_FUNCTION_LIST,
                    "variables": {},
                }
            )
            response = Utility.json_loads(response)
            mcp_functions = response["data"]["mcpFunctionList"]["mcpFunctionList"]
            tools = list(filter(lambda x: x.get("mcpType") == "tool", mcp_functions))
            resources = list(
                filter(lambda x: x.get("mcpType") == "resource", mcp_functions)
            )
            prompts = list(
                filter(lambda x: x.get("mcpType") == "prompt", mcp_functions)
            )

            mcp_configuration = {
                "tools": {
                    "tools": [
                        dict(
                            {
                                "name": tool["name"],
                                "description": tool.get("description"),
                                "annotations": tool.get("annotations"),
                            },
                            **tool.get("data", {}),
                        )
                        for tool in tools
                    ],
                    "tool_modules": [
                        {
                            "name": tool["name"],
                            "module_name": tool["moduleName"],
                            "function_name": tool["functionName"],
                            "setting": tool.get("setting"),
                            "return_type": (
                                "text"
                                if tool.get("returnType") is None
                                else tool.get("returnType")
                            ),
                            "source": tool.get("source"),
                        }
                        for tool in tools
                    ],
                },
                "resources": {
                    "resources": [
                        dict(
                            {
                                "name": resource["name"],
                                "description": resource.get("description"),
                                "annotations": resource.get("annotations"),
                            },
                            **resource.get("data", {}),
                        )
                        for resource in resources
                    ],
                    "resource_modules": [
                        {
                            "name": resource["name"],
                            "module_name": resource["moduleName"],
                            "function_name": resource["functionName"],
                            "setting": resource.get("setting"),
                            "source": resource.get("source"),
                        }
                        for resource in resources
                    ],
                },
                "prompts": {
                    "prompts": [
                        dict(
                            {
                                "name": prompt["name"],
                                "description": prompt.get("description"),
                                "annotations": prompt.get("annotations"),
                            },
                            **prompt.get("data", {}),
                        )
                        for prompt in prompts
                    ],
                    "prompt_modules": [
                        {
                            "name": prompt["name"],
                            "module_name": prompt["moduleName"],
                            "function_name": prompt["functionName"],
                            "setting": prompt.get("setting"),
                            "source": prompt.get("source"),
                        }
                        for prompt in prompts
                    ],
                },
            }

            cls.mcp_configuration[endpoint_id] = mcp_configuration

        return cls.mcp_configuration[endpoint_id]
