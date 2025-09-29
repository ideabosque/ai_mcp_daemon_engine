# -*- coding: utf-8 -*-
from __future__ import annotations

__author__ = "bibow"

import logging
from functools import lru_cache
from typing import Any, Dict, Optional, Set

from silvaengine_dynamodb_base.cache_utils import (
    CacheConfigResolvers,
    CascadingCachePurger,
)




def _extract_module_setting_ids(raw_classes: Any) -> Set[str]:
    setting_ids: Set[str] = set()
    if not raw_classes:
        return setting_ids

    for class_item in raw_classes:
        if class_item is None:
            continue

        payload = class_item
        if hasattr(class_item, "as_dict"):
            try:
                payload = class_item.as_dict()
            except Exception:
                payload = None
        elif hasattr(class_item, "attribute_values"):
            payload = getattr(class_item, "attribute_values", None)

        if payload is None:
            continue

        if not isinstance(payload, dict):
            try:
                payload = dict(payload)
            except Exception:
                continue

        setting_id = payload.get("setting_id")
        if isinstance(setting_id, str) and setting_id:
            setting_ids.add(setting_id)

    return setting_ids

@lru_cache(maxsize=1)
def _get_cascading_cache_purger() -> CascadingCachePurger:
    from ..handlers.config import Config

    return CascadingCachePurger(
        CacheConfigResolvers(
            get_cache_entity_config=Config.get_cache_entity_config,
            get_cache_relationships=Config.get_cache_relationships,
            queries_module_base="ai_mcp_daemon_engine.queries",
        )
    )


def purge_entity_cascading_cache(
    logger: logging.Logger,
    entity_type: str,
    *,
    context_keys: Optional[Dict[str, Any]] = None,
    entity_keys: Optional[Dict[str, Any]] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    """Universal entry point for cascading cache purging."""
    purger = _get_cascading_cache_purger()
    return purger.purge_entity_cascading_cache(
        logger,
        entity_type,
        context_keys=context_keys,
        entity_keys=entity_keys,
        cascade_depth=cascade_depth,
    )


def purge_mcp_module_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    module_name: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    entity_keys = {"module_name": module_name} if module_name else None
    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_module",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys,
        cascade_depth=cascade_depth,
    )
    if module_name:
        result.setdefault("entity_keys", {})["module_name"] = module_name
    return result


def purge_mcp_function_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    name: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    entity_keys = {"name": name} if name else None
    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_function",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys,
        cascade_depth=cascade_depth,
    )
    if name:
        result.setdefault("entity_keys", {})["name"] = name
    return result


def purge_mcp_function_call_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    mcp_function_call_uuid: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    entity_keys = (
        {"mcp_function_call_uuid": mcp_function_call_uuid}
        if mcp_function_call_uuid
        else None
    )
    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_function_call",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys,
        cascade_depth=cascade_depth,
    )
    if mcp_function_call_uuid:
        result.setdefault("entity_keys", {})[
            "mcp_function_call_uuid"
        ] = mcp_function_call_uuid
    return result


def purge_mcp_setting_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    setting_id: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    entity_keys = {"setting_id": setting_id} if setting_id else None
    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_setting",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys,
        cascade_depth=cascade_depth,
    )
    if setting_id:
        result.setdefault("entity_keys", {})["setting_id"] = setting_id
    return result


__all__ = [
    "purge_entity_cascading_cache",
    "purge_mcp_module_cascading_cache",
    "purge_mcp_function_cascading_cache",
    "purge_mcp_function_call_cascading_cache",
    "purge_mcp_setting_cascading_cache",
]
