#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo

from ..models import mcp_module
from ..types.mcp_module import MCPModuleListType, MCPModuleType


def resolve_mcp_module(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPModuleType:
    return mcp_module.resolve_mcp_module(info, **kwargs)


def resolve_mcp_module_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPModuleListType:
    return mcp_module.resolve_mcp_module_list(info, **kwargs)