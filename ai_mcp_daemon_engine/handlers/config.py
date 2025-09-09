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
        $className: String, 
        $functionName: String
    ) {
    mcpFunctionList(
        pageNumber: $pageNumber, 
        limit: $limit, 
        mcpType: $mcpType, 
        moduleName: $moduleName, 
        className: $className, 
        functionName: $functionName
    ) {
        pageSize pageNumber total mcpFunctionList { 
            endpointId 
            name 
            mcpType 
            description 
            data 
            annotations 
            moduleName 
            className 
            functionName 
            returnType 
            updatedBy 
            createdAt 
            updatedAt 
        }
    }
}"""

MCP_MODULE = """query mcpModule($moduleName: String!) {
    mcpModule(moduleName: $moduleName) {
        endpointId 
        moduleName 
        packageName 
        classes 
        source 
        updatedBy 
        createdAt 
        updatedAt
    }
}"""

MCP_SETTING = """query mcpSetting($settingId: String!) {
    mcpSetting(settingId: $settingId) {
        endpointId 
        settingId 
        setting 
        updatedBy 
        createdAt 
        updatedAt
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
    sse_clients: Dict[int, asyncio.Queue] = {}
    user_clients: dict[str, set[int]] = {}
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
            if cls.transport == "sse" and cls.auth_provider == "local":
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
        cls.transport = setting.get("transport", "sse")
        cls.port = setting.get("port", 8000)
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
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetches and caches MCP configuration for a given endpoint.

        Args:
            endpoint_id: ID of the endpoint to fetch configuration from
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            Dict containing the complete MCP configuration

        Raises:
            Exception: If GraphQL queries fail or data is malformed
        """
        # Check if configuration exists in cache and force_refresh is not requested
        if not force_refresh and cls.mcp_configuration.get(endpoint_id) is not None:
            return cls.mcp_configuration[endpoint_id]

        if cls.logger:
            cls.logger.info(f"Fetching MCP configuration for endpoint: {endpoint_id}")

        try:
            # Step 1: Fetch all MCP functions
            response = cls.mcp_core.mcp_core_graphql(
                endpoint_id=endpoint_id,
                query=MCP_FUNCTION_LIST,
                variables={},
            )
            response = Utility.json_loads(response)

            if "errors" in response:
                cls.logger.error(
                    f"GraphQL errors in MCP_FUNCTION_LIST: {response['errors']}"
                )
                raise Exception(f"Failed to fetch MCP functions: {response['errors']}")

            if (
                not response.get("data", {})
                .get("mcpFunctionList", {})
                .get("mcpFunctionList")
            ):
                cls.logger.warning(
                    f"No MCP functions found for endpoint: {endpoint_id}"
                )
                mcp_functions = []
            else:
                mcp_functions = response["data"]["mcpFunctionList"]["mcpFunctionList"]

            # Step 2: Categorize functions by type
            tools = [func for func in mcp_functions if func.get("mcpType") == "tool"]
            resources = [
                func for func in mcp_functions if func.get("mcpType") == "resource"
            ]
            prompts = [
                func for func in mcp_functions if func.get("mcpType") == "prompt"
            ]

            if cls.logger:
                cls.logger.info(
                    f"Found {len(tools)} tools, {len(resources)} resources, {len(prompts)} prompts"
                )

            # Step 3: Build initial configuration structure
            mcp_configuration = {
                "tools": [cls._build_function_config(tool) for tool in tools],
                "resources": [
                    cls._build_function_config(resource) for resource in resources
                ],
                "prompts": [cls._build_function_config(prompt) for prompt in prompts],
                "module_links": [
                    cls._build_module_link(func)
                    for func in mcp_functions
                    if func.get("moduleName") and func.get("className")
                ],
                "modules": [],
            }

            # Step 4: Fetch module and setting information
            modules_info = cls._fetch_modules_and_settings(
                endpoint_id, mcp_configuration["module_links"]
            )
            mcp_configuration["modules"] = modules_info

            # Step 5: Cache the configuration
            cls.mcp_configuration[endpoint_id] = mcp_configuration

            if cls.logger:
                cls.logger.info(
                    f"Successfully cached MCP configuration for endpoint: {endpoint_id}"
                )

            return mcp_configuration

        except Exception as e:
            if cls.logger:
                cls.logger.error(
                    f"Failed to fetch MCP configuration for {endpoint_id}: {e}"
                )
            raise

    @classmethod
    def _build_function_config(cls, func: Dict[str, Any]) -> Dict[str, Any]:
        """Build function configuration with safe data extraction."""
        base_config = {
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "annotations": func.get("annotations", {}),
        }

        # Safely merge data field
        func_data = func.get("data", {})
        if isinstance(func_data, dict):
            base_config.update(func_data)

        return base_config

    @classmethod
    def _build_module_link(cls, func: Dict[str, Any]) -> Dict[str, Any]:
        """Build module link with proper field mapping."""
        return {
            "type": func.get("mcpType", ""),  # Fixed: was "type" should be "mcpType"
            "name": func.get("name", ""),
            "module_name": func.get("moduleName", ""),
            "class_name": func.get("className", ""),
            "function_name": func.get("functionName", ""),
            "return_type": func.get("returnType", "text"),  # Default to "text"
        }

    @classmethod
    def _fetch_modules_and_settings(
        cls, endpoint_id: str, module_links: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fetch module and setting information efficiently."""
        modules_info = []

        # Group by module to reduce GraphQL calls
        modules_classes = {}
        for link in module_links:
            module_name = link.get("module_name")
            class_name = link.get("class_name")

            if not module_name or not class_name:
                if cls.logger:
                    cls.logger.warning(
                        f"Skipping module link with missing module_name or class_name: {link}"
                    )
                continue

            if module_name not in modules_classes:
                modules_classes[module_name] = set()
            modules_classes[module_name].add(class_name)

        # Process each module
        for module_name, class_names in modules_classes.items():
            try:
                # Fetch module information
                module_response = cls.mcp_core.mcp_core_graphql(
                    endpoint_id=endpoint_id,
                    query=MCP_MODULE,
                    variables={"moduleName": module_name},
                )
                module_response = Utility.json_loads(module_response)

                if "errors" in module_response:
                    if cls.logger:
                        cls.logger.error(
                            f"Error fetching module {module_name}: {module_response['errors']}"
                        )
                    continue

                module_data = module_response.get("data", {}).get("mcpModule")
                if not module_data:
                    if cls.logger:
                        cls.logger.warning(f"No data found for module: {module_name}")
                    continue

                # Batch fetch settings for all classes in this module
                setting_ids = []
                class_to_setting_map = {}

                for class_name in class_names:
                    matching_class = next(
                        (
                            c
                            for c in module_data.get("classes", [])
                            if c.get("class_name") == class_name
                        ),
                        None,
                    )

                    if not matching_class:
                        if cls.logger:
                            cls.logger.warning(
                                f"Class '{class_name}' not found in module '{module_name}'"
                            )
                        continue

                    setting_id = matching_class.get("setting_id")
                    if setting_id:
                        setting_ids.append(setting_id)
                        class_to_setting_map[class_name] = {
                            "setting_id": setting_id,
                            "class_info": matching_class,
                        }

                # Fetch settings (could be optimized further with batch query if available)
                for class_name, class_info in class_to_setting_map.items():
                    try:
                        setting_response = cls.mcp_core.mcp_core_graphql(
                            endpoint_id=endpoint_id,
                            query=MCP_SETTING,
                            variables={"settingId": class_info["setting_id"]},
                        )
                        setting_response = Utility.json_loads(setting_response)

                        if "errors" in setting_response:
                            if cls.logger:
                                cls.logger.error(
                                    f"Error fetching setting {class_info['setting_id']}: {setting_response['errors']}"
                                )
                            setting_data = {}
                        else:
                            setting_data = (
                                setting_response.get("data", {})
                                .get("mcpSetting", {})
                                .get("setting", {})
                            )

                        # Build module info
                        module_info = {
                            "module_name": module_name,
                            "package_name": module_data.get("packageName", module_name),
                            "class_name": class_name,
                            "setting": setting_data,
                            "source": module_data.get("source", ""),
                        }
                        modules_info.append(module_info)

                    except Exception as e:
                        if cls.logger:
                            cls.logger.error(
                                f"Error processing setting for {module_name}.{class_name}: {e}"
                            )
                        # Add module info with empty setting as fallback
                        module_info = {
                            "module_name": module_name,
                            "package_name": module_data.get("packageName", module_name),
                            "class_name": class_name,
                            "setting": {},
                            "source": module_data.get("source", ""),
                        }
                        modules_info.append(module_info)

            except Exception as e:
                if cls.logger:
                    cls.logger.error(f"Error processing module {module_name}: {e}")
                continue

        return modules_info

    @classmethod
    def refresh_mcp_configuration(cls, endpoint_id: str) -> Dict[str, Any]:
        """Force refresh of MCP configuration for an endpoint."""
        return cls.fetch_mcp_configuration(endpoint_id, force_refresh=True)

    @classmethod
    def clear_mcp_configuration_cache(cls, endpoint_id: str = None):
        """Clear MCP configuration cache for specific endpoint or all endpoints."""
        if endpoint_id:
            cls.mcp_configuration.pop(endpoint_id, None)
            if cls.logger:
                cls.logger.info(
                    f"Cleared MCP configuration cache for endpoint: {endpoint_id}"
                )
        else:
            cls.mcp_configuration.clear()
            if cls.logger:
                cls.logger.info("Cleared all MCP configuration cache")
