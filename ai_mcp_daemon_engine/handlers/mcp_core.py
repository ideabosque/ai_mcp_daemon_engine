#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import logging
from typing import Any, Dict

from graphene import Schema
from silvaengine_dynamodb_base import BaseModel
from silvaengine_utility import Graphql

from .schema import Mutations, Query, type_class


class MCPCore(Graphql):
    def __init__(self, logger: logging.Logger, **setting: Dict[str, Any]) -> None:
        Graphql.__init__(self, logger, **setting)

        if (
            setting.get("region_name")
            and setting.get("aws_access_key_id")
            and setting.get("aws_secret_access_key")
        ):
            BaseModel.Meta.region = setting.get("region_name")
            BaseModel.Meta.aws_access_key_id = setting.get("aws_access_key_id")
            BaseModel.Meta.aws_secret_access_key = setting.get("aws_secret_access_key")

    def mcp_core_graphql(self, **params: Dict[str, Any]) -> Any:
        try:
            print(f">> mcp_core_graphql {'#'}*80 {params}")
            schema = Schema(
                query=Query,
                mutation=Mutations,
                types=type_class(),
            )
            return self.execute(schema, **params)
        except Exception as e:
            raise e
