#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from graphene import DateTime, List, ObjectType, String

from silvaengine_dynamodb_base import ListObjectType
from silvaengine_utility import JSON


class MCPSettingType(ObjectType):
    endpoint_id = String()
    setting_id = String()
    setting = JSON()
    updated_by = String()
    created_at = DateTime()
    updated_at = DateTime()


class MCPSettingListType(ListObjectType):
    mcp_setting_list = List(MCPSettingType)