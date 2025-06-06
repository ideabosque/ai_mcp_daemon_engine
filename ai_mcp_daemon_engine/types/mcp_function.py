#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from graphene import DateTime, Int, List, ObjectType, String

from silvaengine_dynamodb_base import ListObjectType
from silvaengine_utility import JSON


class MCPFunctionType(ObjectType):
    endpoint_id = String()
    name = String()
    type = String()
    description = String()
    data = JSON()
    annotations = String()
    module_name = String()
    function_name = String()
    setting = JSON()
    source = String()
    updated_by = String()
    created_at = DateTime()
    updated_at = DateTime()


class MCPFunctionListType(ListObjectType):
    mcp_function_list = List(MCPFunctionType)
