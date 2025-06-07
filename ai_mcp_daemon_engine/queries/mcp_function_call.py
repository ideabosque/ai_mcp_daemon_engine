#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo

from ..models import mcp_function_call
from ..types.mcp_function_call import MCPFunctionCallListType, MCPFunctionCallType


def resolve_mcp_function_call(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPFunctionCallType:
    return mcp_function_call.resolve_mcp_function_call(info, **kwargs)


def resolve_mcp_function_call_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPFunctionCallListType:
    return mcp_function_call.resolve_mcp_function_call_list(info, **kwargs)
