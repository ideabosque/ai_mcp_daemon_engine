#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import functools
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
from silvaengine_utility import Utility, method_cache

from ..handlers.config import Config
from ..types.mcp_setting import MCPSettingListType, MCPSettingType


class MCPSettingModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "mcp-settings"

    endpoint_id = UnicodeAttribute(hash_key=True)
    setting_id = UnicodeAttribute(range_key=True)
    setting = MapAttribute()
    updated_by = UnicodeAttribute()
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()


def purge_cache():
    def actual_decorator(original_function):
        @functools.wraps(original_function)
        def wrapper_function(*args, **kwargs):
            try:
                # Use cascading cache purging for mcp settings
                from ..models.cache import purge_mcp_setting_cascading_cache

                cache_result = purge_mcp_setting_cascading_cache(
                    logger=args[0].context.get("logger"),
                    endpoint_id=args[0].context.get("endpoint_id")
                    or kwargs.get("endpoint_id"),
                    setting_id=kwargs.get("setting_id"),
                )

                ## Original function.
                result = original_function(*args, **kwargs)

                return result
            except Exception as e:
                log = traceback.format_exc()
                args[0].context.get("logger").error(log)
                raise e

        return wrapper_function

    return actual_decorator


def create_mcp_setting_table(logger: logging.Logger) -> bool:
    """Create the MCP Setting table if it doesn't exist."""
    if not MCPSettingModel.exists():
        # Create with on-demand billing (PAY_PER_REQUEST)
        MCPSettingModel.create_table(billing_mode="PAY_PER_REQUEST", wait=True)
        logger.info("The MCP Setting table has been created.")
    return True


@retry(
    reraise=True,
    wait=wait_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(5),
)
@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("models", "mcp_setting"),
)
def get_mcp_setting(endpoint_id: str, setting_id: str) -> MCPSettingModel:
    return MCPSettingModel.get(endpoint_id, setting_id)


def get_mcp_setting_count(endpoint_id: str, setting_id: str) -> int:
    return MCPSettingModel.count(endpoint_id, MCPSettingModel.setting_id == setting_id)


def get_mcp_setting_type(
    info: ResolveInfo, mcp_setting: MCPSettingModel
) -> MCPSettingType:
    try:
        mcp_setting = mcp_setting.__dict__["attribute_values"]
    except Exception as e:
        log = traceback.format_exc()
        info.context.get("logger").exception(log)
        raise e
    return MCPSettingType(**Utility.json_normalize(mcp_setting))


def resolve_mcp_setting(info: ResolveInfo, **kwargs: Dict[str, Any]) -> MCPSettingType:
    count = get_mcp_setting_count(info.context["endpoint_id"], kwargs["setting_id"])
    if count == 0:
        return None

    return get_mcp_setting_type(
        info, get_mcp_setting(info.context["endpoint_id"], kwargs["setting_id"])
    )


@monitor_decorator
@resolve_list_decorator(
    attributes_to_get=["endpoint_id", "setting_id"],
    list_type_class=MCPSettingListType,
    type_funct=get_mcp_setting_type,
)
def resolve_mcp_setting_list(info: ResolveInfo, **kwargs: Dict[str, Any]) -> Any:
    endpoint_id = info.context["endpoint_id"]
    setting_id = kwargs.get("setting_id")

    args = []
    inquiry_funct = MCPSettingModel.scan
    count_funct = MCPSettingModel.count
    if endpoint_id:
        args = [endpoint_id, None]
        inquiry_funct = MCPSettingModel.query
    the_filters = None
    if setting_id:
        the_filters &= MCPSettingModel.setting_id.contains(setting_id)
    if the_filters is not None:
        args.append(the_filters)

    return inquiry_funct, count_funct, args


@purge_cache()
@insert_update_decorator(
    keys={
        "hash_key": "endpoint_id",
        "range_key": "setting_id",
    },
    range_key_required=False,
    model_funct=get_mcp_setting,
    count_funct=get_mcp_setting_count,
    type_funct=get_mcp_setting_type,
)
def insert_update_mcp_setting(info: ResolveInfo, **kwargs: Dict[str, Any]) -> None:

    endpoint_id = kwargs.get("endpoint_id")
    setting_id = kwargs.get("setting_id")

    if kwargs.get("entity") is None:
        cols = {
            "setting": kwargs.get("setting", {}),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }

        MCPSettingModel(
            endpoint_id,
            setting_id,
            **cols,
        ).save()
        return

    mcp_setting = kwargs.get("entity")
    actions = [
        MCPSettingModel.updated_by.set(kwargs["updated_by"]),
        MCPSettingModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "setting": MCPSettingModel.setting,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(kwargs[key]))

    mcp_setting.update(actions=actions)
    return


@purge_cache()
@delete_decorator(
    keys={
        "hash_key": "endpoint_id",
        "range_key": "setting_id",
    },
    model_funct=get_mcp_setting,
)
def delete_mcp_setting(info: ResolveInfo, **kwargs: Dict[str, Any]) -> bool:

    kwargs["entity"].delete()
    return True
