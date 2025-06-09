#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import time
from typing import Any, Dict

from graphene import (
    Boolean,
    DateTime,
    Field,
    Int,
    List,
    ObjectType,
    ResolveInfo,
    String,
)

from ..mutations.mcp_function import DeleteMcpFunction, InsertUpdateMcpFunction
from ..mutations.mcp_function_call import (
    DeleteMcpFunctionCall,
    InsertUpdateMcpFunctionCall,
)
from ..queries.mcp_function import resolve_mcp_function, resolve_mcp_function_list
from ..queries.mcp_function_call import (
    resolve_mcp_function_call,
    resolve_mcp_function_call_list,
)
from ..types.mcp_function import MCPFunctionListType, MCPFunctionType
from ..types.mcp_function_call import MCPFunctionCallListType, MCPFunctionCallType


def type_class():
    return [
        MCPFunctionType,
        MCPFunctionListType,
        MCPFunctionCallType,
        MCPFunctionCallListType,
    ]


class Query(ObjectType):
    ping = String()

    mcp_function = Field(
        MCPFunctionType,
        name=String(required=True),
    )

    mcp_function_list = Field(
        MCPFunctionListType,
        page_number=Int(required=False),
        limit=Int(required=False),
        mcp_type=String(required=False),
        description=String(required=False),
        module_name=String(required=False),
        function_name=String(required=False),
    )

    mcp_function_call = Field(
        MCPFunctionCallType,
        mcp_function_call_uuid=String(required=True),
    )

    mcp_function_call_list = Field(
        MCPFunctionCallListType,
        page_number=Int(required=False),
        limit=Int(required=False),
        mcp_type=String(required=False),
        name=String(required=False),
        status=String(required=False),
    )

    def resolve_ping(self, info: ResolveInfo) -> str:
        return f"Hello at {time.strftime('%X')}!!"

    def resolve_mcp_function(
        self, info: ResolveInfo, **kwargs: Dict[str, Any]
    ) -> MCPFunctionType:
        return resolve_mcp_function(info, **kwargs)

    def resolve_mcp_function_list(
        self, info: ResolveInfo, **kwargs: Dict[str, Any]
    ) -> MCPFunctionListType:
        return resolve_mcp_function_list(info, **kwargs)

    def resolve_mcp_function_call(
        self, info: ResolveInfo, **kwargs: Dict[str, Any]
    ) -> MCPFunctionCallType:
        return resolve_mcp_function_call(info, **kwargs)

    def resolve_mcp_function_call_list(
        self, info: ResolveInfo, **kwargs: Dict[str, Any]
    ) -> MCPFunctionCallListType:
        return resolve_mcp_function_call_list(info, **kwargs)


class Mutations(ObjectType):
    insert_update_mcp_function = InsertUpdateMcpFunction.Field()
    delete_mcp_function = DeleteMcpFunction.Field()
    insert_update_mcp_function_call = InsertUpdateMcpFunctionCall.Field()
    delete_mcp_function_call = DeleteMcpFunctionCall.Field()
