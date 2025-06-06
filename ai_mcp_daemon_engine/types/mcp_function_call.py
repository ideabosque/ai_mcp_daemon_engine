#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from graphene import DateTime, Int, List, ObjectType, String

from silvaengine_dynamodb_base import ListObjectType
from silvaengine_utility import JSON


class MCPFunctionCallType(ObjectType):
    endpoint_id = String()
    mcp_function_call_uuid = String()
    type = String()
    name = String()
    arguments = JSON()
    content = String()
    status = String()
    notes = String()
    time_spent = Int()
    updated_by = String()
    created_at = DateTime()
    updated_at = DateTime()


class MCPFunctionCallListType(ListObjectType):
    mcp_function_call_list = List(MCPFunctionCallType)
