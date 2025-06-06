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

from ..types.mcp_function_call import MCPFunctionCallListType, MCPFunctionCallType


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


class NameIndex(LocalSecondaryIndex):
    """
    This class represents a local secondary index
    """

    class Meta:
        billing_mode = "PAY_PER_REQUEST"
        # All attributes are projected
        projection = AllProjection()
        index_name = "name-index"

    endpoint_id = UnicodeAttribute(hash_key=True)
    name = UnicodeAttribute(range_key=True)


class MCPFunctionCallModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "mcp-function-calls"

    endpoint_id = UnicodeAttribute(hash_key=True)
    mcp_function_call_uuid = UnicodeAttribute(range_key=True)
    name = UnicodeAttribute()
    type = UnicodeAttribute()
    arguments = MapAttribute()
    content = UnicodeAttribute(null=True)
    status = UnicodeAttribute(default="initial")
    notes = UnicodeAttribute(null=True)
    time_spent = NumberAttribute(null=True)
    updated_by = UnicodeAttribute()
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()
    type_index = TypeIndex()
    name_index = NameIndex()


def create_mcp_function_table(logger: logging.Logger) -> bool:
    """Create the MCP Function table if it doesn't exist."""
    if not MCPFunctionCallModel.exists():
        # Create with on-demand billing (PAY_PER_REQUEST)
        MCPFunctionCallModel.create_table(billing_mode="PAY_PER_REQUEST", wait=True)
        logger.info("The MCP Function table has been created.")
    return True
