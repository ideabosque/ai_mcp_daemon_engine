# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import logging


def _initialize_tables(logger: logging.Logger) -> None:
    from .mcp_function import create_mcp_function_table
    from .mcp_function_call import create_mcp_function_call_table

    create_mcp_function_table(logger)
    create_mcp_function_call_table(logger)
