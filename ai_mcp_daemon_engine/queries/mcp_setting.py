#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from typing import Any, Dict

from graphene import ResolveInfo

from ..models import mcp_setting
from ..types.mcp_setting import MCPSettingListType, MCPSettingType


def resolve_mcp_setting(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPSettingType:
    return mcp_setting.resolve_mcp_setting(info, **kwargs)


def resolve_mcp_setting_list(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPSettingListType:
    return mcp_setting.resolve_mcp_setting_list(info, **kwargs)