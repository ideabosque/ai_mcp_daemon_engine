# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import asyncio
import logging
from typing import Any, Dict


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
