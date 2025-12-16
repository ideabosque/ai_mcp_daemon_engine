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
    BooleanAttribute,
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
from silvaengine_utility import method_cache
from silvaengine_utility.serializer import Serializer
from ..handlers.config import Config
from ..types.mcp_function_call import MCPFunctionCallListType, MCPFunctionCallType


class MCPTypeIndex(LocalSecondaryIndex):
    """
    This class represents a local secondary index
    """

    class Meta:
        billing_mode = "PAY_PER_REQUEST"
        # All attributes are projected
        projection = AllProjection()
        index_name = "mcp_type-index"

    partition_key = UnicodeAttribute(hash_key=True)
    mcp_type = UnicodeAttribute(range_key=True)


class NameIndex(LocalSecondaryIndex):
    """
    This class represents a local secondary index
    """

    class Meta:
        billing_mode = "PAY_PER_REQUEST"
        # All attributes are projected
        projection = AllProjection()
        index_name = "name-index"

    partition_key = UnicodeAttribute(hash_key=True)
    name = UnicodeAttribute(range_key=True)


class MCPFunctionCallModel(BaseModel):
    class Meta(BaseModel.Meta):
        table_name = "mcp-function-calls"

    partition_key = UnicodeAttribute(hash_key=True)
    mcp_function_call_uuid = UnicodeAttribute(range_key=True)
    name = UnicodeAttribute()
    mcp_type = UnicodeAttribute()
    arguments = MapAttribute()
    has_content = BooleanAttribute(default=False)
    status = UnicodeAttribute(default="initial")
    notes = UnicodeAttribute(null=True)
    time_spent = NumberAttribute(null=True)
    updated_by = UnicodeAttribute()
    created_at = UTCDateTimeAttribute()
    updated_at = UTCDateTimeAttribute()
    mcp_type_index = MCPTypeIndex()
    name_index = NameIndex()


def purge_cache():
    def actual_decorator(original_function):
        @functools.wraps(original_function)
        def wrapper_function(*args, **kwargs):
            try:
                # Use cascading cache purging for mcp function calls
                from ..models.cache import purge_entity_cascading_cache

                partition_key = args[0].context.get("partition_key") or kwargs.get(
                    "partition_key"
                )
                entity_keys = {}
                if kwargs.get("mcp_function_call_uuid"):
                    entity_keys["mcp_function_call_uuid"] = kwargs.get(
                        "mcp_function_call_uuid"
                    )

                result = purge_entity_cascading_cache(
                    args[0].context.get("logger"),
                    entity_type="mcp_function_call",
                    context_keys={"partition_key": partition_key} if partition_key else None,
                    entity_keys=entity_keys if entity_keys else None,
                    cascade_depth=3,
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


def create_mcp_function_call_table(logger: logging.Logger) -> bool:
    """Create the MCP Function Call table if it doesn't exist."""
    if not MCPFunctionCallModel.exists():
        # Create with on-demand billing (PAY_PER_REQUEST)
        MCPFunctionCallModel.create_table(billing_mode="PAY_PER_REQUEST", wait=True)
        logger.info("The MCP Function Call table has been created.")
    return True


@retry(
    reraise=True,
    wait=wait_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(5),
)
@method_cache(
    ttl=Config.get_cache_ttl(),
    cache_name=Config.get_cache_name("models", "mcp_function_call"),
)
def get_mcp_function_call(
    partition_key: str, mcp_function_call_uuid: str
) -> MCPFunctionCallModel:
    return MCPFunctionCallModel.get(partition_key, mcp_function_call_uuid)


def get_mcp_function_call_count(partition_key: str, mcp_function_call_uuid: str) -> int:
    return MCPFunctionCallModel.count(
        partition_key,
        MCPFunctionCallModel.mcp_function_call_uuid == mcp_function_call_uuid,
    )


def get_mcp_function_call_type(
    info: ResolveInfo, mcp_function_call_model: MCPFunctionCallModel
) -> MCPFunctionCallType:
    try:
        if mcp_function_call_model.has_content:
            from ..handlers.config import Config

            s3_key = f"mcp_content/{mcp_function_call_model.mcp_function_call_uuid}.json"
            try:
                response = Config.aws_s3.get_object(
                    Bucket=Config.funct_bucket_name, Key=s3_key
                )
                content = response["Body"].read().decode("utf-8")
            except Exception as e:
                raise e
    except Exception as e:
        log = traceback.format_exc()
        info.context.get("logger").exception(log)
        raise e
    mcp_function_call: Dict[str, Any] = mcp_function_call_model.__dict__["attribute_values"]
    has_content = mcp_function_call.pop("has_content")
    if has_content:
        mcp_function_call["content"] = content
    return MCPFunctionCallType(**Serializer.json_normalize(mcp_function_call))


def resolve_mcp_function_call(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> MCPFunctionCallType | None:
    count = get_mcp_function_call_count(
        info.context["partition_key"], kwargs["mcp_function_call_uuid"]
    )
    if count == 0:
        return None

    return get_mcp_function_call_type(
        info,
        get_mcp_function_call(
            info.context["partition_key"], kwargs["mcp_function_call_uuid"]
        ),
    )


@monitor_decorator
@resolve_list_decorator(
    attributes_to_get=["partition_key", "mcp_function_call_uuid", "name", "type"],
    list_type_class=MCPFunctionCallListType,
    type_funct=get_mcp_function_call_type,
)
def resolve_mcp_function_call_list(info: ResolveInfo, **kwargs: Dict[str, Any]) -> Any:
    partition_key = info.context["partition_key"]
    mcp_type = kwargs.get("mcp_type")
    name = kwargs.get("name")
    status = kwargs.get("status")

    args = []
    inquiry_funct = MCPFunctionCallModel.scan
    count_funct = MCPFunctionCallModel.count
    if partition_key:
        args = [partition_key, None]
        inquiry_funct = MCPFunctionCallModel.query
        if mcp_type:
            inquiry_funct = MCPFunctionCallModel.mcp_type_index.query
            args[1] = MCPFunctionCallModel.mcp_type == mcp_type
            count_funct = MCPFunctionCallModel.mcp_type_index.count
        elif name:
            inquiry_funct = MCPFunctionCallModel.name_index.query
            args[1] = MCPFunctionCallModel.name == name
            count_funct = MCPFunctionCallModel.name_index.count

    the_filters = None
    if status:
        the_filters &= MCPFunctionCallModel.status == status
    if the_filters is not None:
        args.append(the_filters)

    return inquiry_funct, count_funct, args


@purge_cache()
@insert_update_decorator(
    keys={
        "hash_key": "partition_key",
        "range_key": "mcp_function_call_uuid",
    },
    model_funct=get_mcp_function_call,
    count_funct=get_mcp_function_call_count,
    type_funct=get_mcp_function_call_type,
)
def insert_update_mcp_function_call(
    info: ResolveInfo, **kwargs: Dict[str, Any]
) -> None:

    partition_key = kwargs.get("partition_key")
    mcp_function_call_uuid = kwargs.get("mcp_function_call_uuid", str(uuid.uuid4()))

    if kwargs.get("entity") is None:
        cols = {
            "name": kwargs["name"],
            "mcp_type": kwargs["mcp_type"],
            "arguments": kwargs.get("arguments", {}),
            "updated_by": kwargs["updated_by"],
            "created_at": pendulum.now("UTC"),
            "updated_at": pendulum.now("UTC"),
        }
        for key in [
            "has_content",
            "status",
            "notes",
            "time_spent",
        ]:
            if key in kwargs:
                cols[key] = kwargs[key]

        MCPFunctionCallModel(
            partition_key,
            mcp_function_call_uuid,
            **cols,
        ).save()
        return

    mcp_function_call = kwargs.get("entity")
    actions = [
        MCPFunctionCallModel.updated_by.set(kwargs["updated_by"]),
        MCPFunctionCallModel.updated_at.set(pendulum.now("UTC")),
    ]

    field_map = {
        "name": MCPFunctionCallModel.name,
        "mcp_type": MCPFunctionCallModel.mcp_type,
        "arguments": MCPFunctionCallModel.arguments,
        "has_content": MCPFunctionCallModel.has_content,
        "status": MCPFunctionCallModel.status,
        "notes": MCPFunctionCallModel.notes,
        "time_spent": MCPFunctionCallModel.time_spent,
    }

    for key, field in field_map.items():
        if key in kwargs:
            actions.append(field.set(kwargs[key]))

    mcp_function_call.update(actions=actions)
    return


@purge_cache()
@delete_decorator(
    keys={
        "hash_key": "partition_key",
        "range_key": "mcp_function_call_uuid",
    },
    model_funct=get_mcp_function_call,
)
def delete_mcp_function_call(info: ResolveInfo, **kwargs: Dict[str, Any]) -> bool:

    kwargs["entity"].delete()
    return True
