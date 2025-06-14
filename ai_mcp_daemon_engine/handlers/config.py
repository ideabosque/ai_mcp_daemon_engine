# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import boto3
from passlib.context import CryptContext
from pydantic import AnyUrl

from silvaengine_utility import Utility

from ..models import utils
from .mcp_core import MCPCore

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


_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class LocalUser:
    username: str
    password_hash: str
    roles: List[str]

    def verify(self, plain: str) -> bool:
        return _pwd.verify(plain, self.password_hash)


class Config:
    """
    Centralized Configuration Class
    Manages shared configuration variables across the application.
    """

    # === SSE Client Registry ===
    sse_clients: Dict[int, asyncio.Queue] = None
    user_clients: dict[str, set[int]] = None
    transport = None
    port = None
    mcp_configuration = {}
    funct_bucket_name = None
    funct_zip_path = None
    funct_extract_path = None
    logger = None
    mcp_core = None
    aws_s3 = None
    aws_cognito_idp = None

    # ----------------- universal -----------------
    auth_provider: str = None  # "local" | "cognito"

    # -------- local-JWT (HS256) settings ---------
    jwt_secret_key: str = None
    jwt_algorithm: str = None
    access_token_exp: int = None  # minutes

    # local users file
    local_user_file: str = None
    _USERS = None

    # static super-admin
    admin_username: str | None = None
    admin_password: str | None = None
    admin_static_token: str | None = None

    # ------------- Cognito settings --------------
    issuer = None
    cognito_app_client_id: str | None = None
    cognito_app_secret: str | None = None
    jwks_endpoint: AnyUrl | None = None
    jwks_cache_ttl: int = None  # seconds

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
            cls._setup_function_paths(setting)
            if cls.transport == "sse":
                cls._USERS = cls._load()
            cls._initialize_mcp_core(logger, setting)
            cls._initialize_aws_services(logger, setting)
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
        cls.user_clients = {}
        cls.transport = setting["transport"]
        cls.port = setting["port"]
        if setting.get("mcp_configuration") is not None:
            cls.mcp_configuration["default"] = setting["mcp_configuration"]
            cls.logger.info("MCP Configuration loaded successfully.")

        cls.auth_provider = setting.get("auth_provider", "local")  # "local" | "cognito"
        cls.jwt_secret_key = setting.get("jwt_secret_key", "CHANGEME")
        cls.jwt_algorithm = setting.get("jwt_algorithm", "HS256")
        cls.access_token_exp = int(setting.get("access_token_exp", 15))
        cls.local_user_file = setting.get("local_user_file", "users.json")
        cls.admin_username = setting.get("admin_username", "admin")
        cls.admin_password = setting.get("admin_password", "admin123")
        cls.admin_static_token = setting.get("admin_static_token", None)
        cls.cognito_app_client_id = setting.get("cognito_app_client_id", None)
        cls.cognito_app_secret = setting.get("cognito_app_secret", None)
        cls.jwks_cache_ttl = int(setting.get("jwks_cache_ttl", 3600))

    @classmethod
    def _setup_function_paths(cls, setting: Dict[str, Any]) -> None:
        cls.funct_bucket_name = setting.get("funct_bucket_name")
        cls.funct_zip_path = (
            "/tmp/funct_zips"
            if setting.get("funct_zip_path") is None
            or setting.get("funct_zip_path") == ""
            else setting["funct_zip_path"]
        )
        cls.funct_extract_path = (
            "/tmp/functs"
            if setting.get("funct_extract_path") is None
            or setting.get("funct_extract_path") == ""
            else setting["funct_extract_path"]
        )
        os.makedirs(cls.funct_zip_path, exist_ok=True)
        os.makedirs(cls.funct_extract_path, exist_ok=True)

    @classmethod
    def _initialize_mcp_core(
        cls, logger: logging.Logger, setting: Dict[str, Any]
    ) -> None:
        """
        Initialize MCP Core with AWS credentials.
        Args:
            logger (logging.Logger): Logger instance for logging
            setting (Dict[str, Any]): Configuration dictionary containing AWS credentials
        """
        if all(
            setting.get(k)
            for k in ["region_name", "aws_access_key_id", "aws_secret_access_key"]
        ):
            cls.mcp_core = MCPCore(logger, **setting)

    @classmethod
    def _initialize_aws_services(
        cls, logger: logging.Logger, setting: Dict[str, Any]
    ) -> None:
        """
        Initialize AWS services including S3 and Cognito IDP clients.
        Args:
            logger (logging.Logger): Logger instance for logging
            setting (Dict[str, Any]): Configuration dictionary containing AWS credentials and settings
        """
        try:
            if all(
                setting.get(k)
                for k in ["region_name", "aws_access_key_id", "aws_secret_access_key"]
            ):
                cls.aws_s3 = boto3.client(
                    "s3",
                    **{
                        "region_name": setting["region_name"],
                        "aws_access_key_id": setting["aws_access_key_id"],
                        "aws_secret_access_key": setting["aws_secret_access_key"],
                    },
                )

            if (
                all(setting.get(k) for k in ["region_name", "cognito_user_pool_id"])
                and cls.auth_provider == "cognito"
            ):
                cls.issuer = f"https://cognito-idp.{setting['region_name']}.amazonaws.com/{setting['cognito_user_pool_id']}"
                cls.jwks_endpoint = (
                    setting.get("cognito_jwks_url")
                    or f"{cls.issuer}/.well-known/jwks.json"
                )
                cls.aws_cognito_idp = boto3.client(
                    "cognito-idp", region_name=setting["region_name"]
                )
        except Exception as e:
            logger.exception("Failed to initialize AWS services configuration.")
            raise e

    @classmethod
    def _initialize_tables(cls, logger: logging.Logger) -> None:
        """
        Initialize database tables by calling the utils._initialize_tables() method.
        This is an internal method used during configuration setup.
        """
        utils._initialize_tables(logger)

    @classmethod
    def _load(cls) -> dict[str, LocalUser]:
        p = Path(cls.local_user_file).expanduser()
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return {u["username"]: LocalUser(**u) for u in raw}

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
            response = cls.mcp_core.mcp_core_graphql(
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
