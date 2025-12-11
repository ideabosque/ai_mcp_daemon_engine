# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import logging


def _initialize_tables(logger: logging.Logger) -> None:
    from .mcp_function import create_mcp_function_table
    from .mcp_function_call import create_mcp_function_call_table
    from .mcp_module import create_mcp_module_table
    from .mcp_setting import create_mcp_setting_table

    create_mcp_function_table(logger)
    create_mcp_function_call_table(logger)
    create_mcp_module_table(logger)
    create_mcp_setting_table(logger)


def _get_cache_ttl():
    """Lazy import to avoid circular dependency"""
    from ..handlers.config import Config

    return Config.get_cache_ttl()


def _get_cache_name(module_type: str, model_name: str):
    """Lazy import to avoid circular dependency"""
    from ..handlers.config import Config

    return Config.get_cache_name(module_type, model_name)
