#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import logging
import traceback
import uuid
from typing import Any, Dict

import pendulum
from graphene import ResolveInfo
from pynamodb.attributes import (
    MapAttribute,
    NumberAttribute,
    UnicodeAttribute,
    UTCDateTimeAttribute,
)
from pynamodb.indexes import AllProjection, LocalSecondaryIndex
from tenacity import retry, stop_after_attempt, wait_exponential

from silvaengine_dynamodb_base import (
    BaseModel,
    delete_decorator,
    insert_update_decorator,
    monitor_decorator,
    resolve_list_decorator,
)
from silvaengine_utility import Utility

from ..types.mcp_function import MCPFunctionListType, MCPFunctionType


class TypeIndex(LocalSecondaryIndex):
    """
    This class represents a local secondary index
    """

    class Meta:
        billing_mode = "PAY_PER_REQUEST"
        # All attributes are projected
        projection = AllProjection()
        index_name = "type-index"

    endpoint_id = UnicodeAttribute(hash_key=True)
    type = UnicodeAttribute(range_key=True)


class MCPFunctionModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "mcp-functions"

    endpoint_id = UnicodeAttribute(hash_key=True)
    name = UnicodeAttribute(range_key=True)
    type = UnicodeAttribute()
    description = UnicodeAttribute(null=True)
    data = MapAttribute()
    annotations = UnicodeAttribute(null=True)
    module_name = UnicodeAttribute(null=True)
    function_name = UnicodeAttribute(null=True)
    setting = MapAttribute()
    source = UnicodeAttribute()
    updated_by = UnicodeAttribute()
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()
    type_index = TypeIndex()


def create_mcp_function_table(logger: logging.Logger) -> bool:
    """Create the MCP Function table if it doesn't exist."""
    if not MCPFunctionModel.exists():
        # Create with on-demand billing (PAY_PER_REQUEST)
        MCPFunctionModel.create_table(billing_mode="PAY_PER_REQUEST", wait=True)
        logger.info("The MCP Function table has been created.")
    return True
