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
    ListAttribute,
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
from ..handlers.config import Config
from silvaengine_utility import Utility, method_cache

from ..types.mcp_module import MCPModuleListType, MCPModuleType


class MCPPackgeIndex(LocalSecondaryIndex):
    """
    This class represents a local secondary index
    """

    class Meta:
        billing_mode = "PAY_PER_REQUEST"
        # All attributes are projected
        projection = AllProjection()
        index_name = "package_name-index"

    endpoint_id = UnicodeAttribute(hash_key=True)
    package_name = UnicodeAttribute(range_key=True)


class MCPModuleModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "mcp-modules"

    endpoint_id = UnicodeAttribute(hash_key=True)
    module_name = UnicodeAttribute(range_key=True)
    package_name = UnicodeAttribute()
    classes = ListAttribute(of=MapAttribute)
    source = UnicodeAttribute(null=True)
    updated_by = UnicodeAttribute()
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()
    mcp_package_index = MCPPackgeIndex()


def create_mcp_module_table(logger: logging.Logger) -> bool:
    """Create the MCP Module table if it doesn't exist."""
    if not MCPModuleModel.exists():
        # Create with on-demand billing (PAY_PER_REQUEST)
        MCPModuleModel.create_table(billing_mode="PAY_PER_REQUEST", wait=True)
        logger.info("The MCP Module table has been created.")
    return True


@retry(
    reraise=True,
    wait=wait_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(5),
)
@method_cache(ttl=Config.get_cache_ttl(), cache_name=Config.get_cache_name('models', 'mcp_module'))
def get_mcp_module(endpoint_id: str, module_name: str) -> MCPModuleModel:
    return MCPModuleModel.get(endpoint_id, module_name)


def get_mcp_module_count(endpoint_id: str, module_name: str) -> int:
    return MCPModuleModel.count(endpoint_id, MCPModuleModel.module_name == module_name)


def get_mcp_module_type(
    info: ResolveInfo, mcp_module: MCPModuleModel
) -> MCPModuleType:
    try:
        mcp_module = mcp_module.__dict__["attribute_values"]
    except Exception as e:
        log = traceback.format_exc()
        info.context.get("logger").exception(log)
        raise e
    return MCPModuleType(**Utility.json_normalize(mcp_module))


def resolve_mcp_module(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPModuleType:
    count = get_mcp_module_count(info.context["endpoint_id"], kwargs["module_name"])
    if count == 0:
        return None

    return get_mcp_module_type(
        info, get_mcp_module(info.context["endpoint_id"], kwargs["module_name"])
    )


@monitor_decorator
@resolve_list_decorator(
    attributes_to_get=["endpoint_id", "module_name", "package_name"],
    list_type_class=MCPModuleListType,
    type_funct=get_mcp_module_type,
)
def resolve_mcp_module_list(info: ResolveInfo, **kwargs: Dict[str, Any]) -> Any:
    endpoint_id = info.context["endpoint_id"]
    package_name = kwargs.get("package_name")
    module_name = kwargs.get("module_name")

    args = []
    inquiry_funct = MCPModuleModel.scan
    count_funct = MCPModuleModel.count
    if endpoint_id:
        args = [endpoint_id, None]
        inquiry_funct = MCPModuleModel.query
        if package_name:
            inquiry_funct = MCPModuleModel.mcp_package_index.query
            args[1] = MCPModuleModel.package_name == package_name
            count_funct = MCPModuleModel.mcp_package_index.count
    the_filters = None
    if module_name:
        the_filters &= MCPModuleModel.module_name.contains(module_name)
    if the_filters is not None:
        args.append(the_filters)

    return inquiry_funct, count_funct, args


@insert_update_decorator(
    keys={
        "hash_key": "endpoint_id",
        "range_key": "module_name",
    },
    range_key_required=True,
    model_funct=get_mcp_module,
    count_funct=get_mcp_module_count,
    type_funct=get_mcp_module_type,
)
def insert_update_mcp_module(info: ResolveInfo, **kwargs: Dict[str, Any]) -> None:
    endpoint_id = kwargs.get("endpoint_id")
    module_name = kwargs.get("module_name")

    if kwargs.get("entity") is None:
        cols = {
            "package_name": kwargs["package_name"],
            "classes": kwargs.get("classes", []),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "source",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        MCPModuleModel(
            endpoint_id,
            module_name,
            **cols,
        ).save()
        return

    mcp_module = kwargs.get("entity")
    actions = [
        MCPModuleModel.updated_by.set(kwargs["updated_by"]),
        MCPModuleModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "package_name": MCPModuleModel.package_name,
        "classes": MCPModuleModel.classes,
        "source": MCPModuleModel.source,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(kwargs[key]))

    mcp_module.update(actions=actions)
    return


@delete_decorator(
    keys={
        "hash_key": "endpoint_id",
        "range_key": "module_name",
    },
    model_funct=get_mcp_module,
)
def delete_mcp_module(info: ResolveInfo, **kwargs: Dict[str, Any]) -> bool:
    kwargs["entity"].delete()
    return True
