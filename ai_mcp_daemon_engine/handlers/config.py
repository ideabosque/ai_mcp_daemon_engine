# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import asyncio
import logging
from typing import Any, Dict

from .mcp_core_engine import MCPCoreEngine


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
    mcp_configuration = None
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
            cls.mcp_configuration = setting["mcp_configuration"]

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
