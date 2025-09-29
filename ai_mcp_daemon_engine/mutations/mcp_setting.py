# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

import traceback
from typing import Any, Dict

from graphene import Boolean, Field, Mutation, String

from silvaengine_utility import JSON

from ..models.mcp_setting import delete_mcp_setting, insert_update_mcp_setting
from ..types.mcp_setting import MCPSettingType


class InsertUpdateMcpSetting(Mutation):
    mcp_setting = Field(MCPSettingType)

    class Arguments:
        setting_id = String(required=False)
        setting = JSON(required=False)
        updated_by = String(required=True)

    @staticmethod
    def mutate(
        root: Any, info: Any, **kwargs: Dict[str, Any]
    ) -> "InsertUpdateMcpSetting":
        try:
            from ..models.cache import purge_mcp_setting_cascading_cache

            purge_mcp_setting_cascading_cache(
                logger=info.context.get("logger"),
                endpoint_id=info.context.get("endpoint_id"),
                setting_id=kwargs.get("setting_id"),
            )

            mcp_setting = insert_update_mcp_setting(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return InsertUpdateMcpSetting(mcp_setting=mcp_setting)


class DeleteMcpSetting(Mutation):
    ok = Boolean()

    class Arguments:
        setting_id = String(required=True)

    @staticmethod
    def mutate(root: Any, info: Any, **kwargs: Dict[str, Any]) -> "DeleteMcpSetting":
        try:
            from ..models.cache import purge_mcp_setting_cascading_cache

            purge_mcp_setting_cascading_cache(
                logger=info.context.get("logger"),
                endpoint_id=info.context.get("endpoint_id"),
                setting_id=kwargs.get("setting_id"),
            )

            ok = delete_mcp_setting(info, **kwargs)
        except Exception as e:
            log = traceback.format_exc()
            info.context.get("logger").error(log)
            raise e

        return DeleteMcpSetting(ok=ok)
