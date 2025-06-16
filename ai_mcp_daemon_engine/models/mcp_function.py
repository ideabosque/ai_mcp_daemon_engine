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


class MCPTypeIndex(LocalSecondaryIndex):
    """
    This class represents a local secondary index
    """

    class Meta:
        billing_mode = "PAY_PER_REQUEST"
        # All attributes are projected
        projection = AllProjection()
        index_name = "mcp_type-index"

    endpoint_id = UnicodeAttribute(hash_key=True)
    mcp_type = UnicodeAttribute(range_key=True)


class MCPFunctionModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "mcp-functions"

    endpoint_id = UnicodeAttribute(hash_key=True)
    name = UnicodeAttribute(range_key=True)
    mcp_type = UnicodeAttribute()
    description = UnicodeAttribute(null=True)
    data = MapAttribute()
    module_name = UnicodeAttribute(null=True)
    function_name = UnicodeAttribute(null=True)
    setting = MapAttribute()
    return_type = UnicodeAttribute(null=True)
    source = UnicodeAttribute(null=True)
    updated_by = UnicodeAttribute()
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()
    mcp_type_index = MCPTypeIndex()


def create_mcp_function_table(logger: logging.Logger) -> bool:
    """Create the MCP Function table if it doesn't exist."""
    if not MCPFunctionModel.exists():
        # Create with on-demand billing (PAY_PER_REQUEST)
        MCPFunctionModel.create_table(billing_mode="PAY_PER_REQUEST", wait=True)
        logger.info("The MCP Function table has been created.")
    return True


@retry(
    reraise=True,
    wait=wait_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(5),
)
def get_mcp_function(endpoint_id: str, name: str) -> MCPFunctionModel:
    return MCPFunctionModel.get(endpoint_id, name)


def get_mcp_function_count(endpoint_id: str, name: str) -> int:
    return MCPFunctionModel.count(endpoint_id, MCPFunctionModel.name == name)


def get_mcp_function_type(
    info: ResolveInfo, mcp_function: MCPFunctionModel
) -> MCPFunctionType:
    try:
        mcp_function = mcp_function.__dict__["attribute_values"]
    except Exception as e:
        log = traceback.format_exc()
        info.context.get("logger").exception(log)
        raise e
    return MCPFunctionType(**Utility.json_loads(Utility.json_dumps(mcp_function)))


def resolve_mcp_function(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPFunctionType:
    count = get_mcp_function_count(info.context["endpoint_id"], kwargs["name"])
    if count == 0:
        return None

    return get_mcp_function_type(
        info, get_mcp_function(info.context["endpoint_id"], kwargs["name"])
    )


@monitor_decorator
@resolve_list_decorator(
    attributes_to_get=["endpoint_id", "name", "type"],
    list_type_class=MCPFunctionListType,
    type_funct=get_mcp_function_type,
)
def resolve_mcp_function_list(info: ResolveInfo, **kwargs: Dict[str, Any]) -> Any:
    endpoint_id = info.context["endpoint_id"]
    mcp_type = kwargs.get("mcp_type")
    description = kwargs.get("description")
    module_name = kwargs.get("module_name")
    function_name = kwargs.get("function_name")

    args = []
    inquiry_funct = MCPFunctionModel.scan
    count_funct = MCPFunctionModel.count
    if endpoint_id:
        args = [endpoint_id, None]
        inquiry_funct = MCPFunctionModel.query
        if mcp_type:
            inquiry_funct = MCPFunctionModel.mcp_type_index.query
            args[1] = MCPFunctionModel.mcp_type == type
            count_funct = MCPFunctionModel.mcp_type_index.count
    the_filters = None
    if description:
        the_filters &= MCPFunctionModel.description.contains(description)
    if module_name:
        the_filters &= MCPFunctionModel.module_name == module_name
    if function_name:
        the_filters &= MCPFunctionModel.function_name == function_name
    if the_filters is not None:
        args.append(the_filters)

    return inquiry_funct, count_funct, args


@insert_update_decorator(
    keys={
        "hash_key": "endpoint_id",
        "range_key": "name",
    },
    range_key_required=True,
    model_funct=get_mcp_function,
    count_funct=get_mcp_function_count,
    type_funct=get_mcp_function_type,
)
def insert_update_mcp_function(info: ResolveInfo, **kwargs: Dict[str, Any]) -> None:
    endpoint_id = kwargs.get("endpoint_id")
    name = kwargs.get("name")

    if kwargs.get("entity") is None:
        cols = {
            "mcp_type": kwargs["mcp_type"],
            "data": kwargs.get("data", {}),
            "setting": kwargs.get("setting", {}),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "description",
            "module_name",
            "function_name",
            "return_type",
            "source",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        MCPFunctionModel(
            endpoint_id,
            name,
            **cols,
        ).save()
        return

    mcp_function = kwargs.get("entity")
    actions = [
        MCPFunctionModel.updated_by.set(kwargs["updated_by"]),
        MCPFunctionModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "mcp_type": MCPFunctionModel.mcp_type,
        "description": MCPFunctionModel.description,
        "data": MCPFunctionModel.data,
        "module_name": MCPFunctionModel.module_name,
        "function_name": MCPFunctionModel.function_name,
        "setting": MCPFunctionModel.setting,
        "return_type": MCPFunctionModel.return_type,
        "source": MCPFunctionModel.source,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(kwargs[key]))

    mcp_function.update(actions=actions)
    return


@delete_decorator(
    keys={
        "hash_key": "endpoint_id",
        "range_key": "name",
    },
    model_funct=get_mcp_function,
)
def delete_mcp_function(info: ResolveInfo, **kwargs: Dict[str, Any]) -> bool:
    kwargs["entity"].delete()
    return True
