#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo

from ..models import mcp_function
from ..types.mcp_function import MCPFunctionListType, MCPFunctionType


def resolve_mcp_function(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPFunctionType:
    return mcp_function.resolve_mcp_function(info, **kwargs)


def resolve_mcp_function_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPFunctionListType:
    return mcp_function.resolve_mcp_function_list(info, **kwargs)
