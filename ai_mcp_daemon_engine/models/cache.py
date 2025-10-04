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
    context_keys: Optional[Dict[str, Any]] = None,
    entity_keys: Optional[Dict[str, Any]] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    """Universal function to purge entity cache with cascading child cache support."""
    purger = _get_cascading_cache_purger()
    return purger.purge_entity_cascading_cache(
        logger,
        entity_type,
        context_keys=context_keys,
        entity_keys=entity_keys,
        cascade_depth=cascade_depth,
    )


# ===============================
# UNIVERSAL CASCADING CACHE PURGING WRAPPERS
# ===============================


def purge_mcp_module_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    module_name: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    """
    MCP module-specific wrapper for the universal cache purging function.

    Args:
        endpoint_id: The endpoint ID
        module_name: Module name (for both individual and child cache clearing)
        cascade_depth: How many levels deep to cascade (default: 3)
        logger: logging.Logger instance

    Returns:
        Dict with comprehensive purge operation results
    """
    entity_keys = {}
    if module_name:
        entity_keys["module_name"] = module_name

    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_module",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys if entity_keys else None,
        cascade_depth=cascade_depth,
    )

    # Transform result for backward compatibility
    mcp_module_result = {
        "module_name": module_name,
        "individual_mcp_module_cache_cleared": result["individual_cache_cleared"],
        "mcp_module_list_cache_cleared": result["list_cache_cleared"],
        "cascaded_levels": result["cascaded_levels"],
        "total_child_caches_cleared": result["total_child_caches_cleared"],
        "total_individual_children_cleared": result.get(
            "total_individual_children_cleared", 0
        ),
        "errors": result["errors"],
    }

    return mcp_module_result


def purge_mcp_function_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    name: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    """
    MCP function-specific wrapper for the universal cache purging function.

    Args:
        endpoint_id: The endpoint ID
        name: Function name (for both individual and child cache clearing)
        cascade_depth: How many levels deep to cascade (default: 3)
        logger: logging.Logger instance

    Returns:
        Dict with comprehensive purge operation results
    """
    entity_keys = {}
    if name:
        entity_keys["name"] = name

    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_function",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys if entity_keys else None,
        cascade_depth=cascade_depth,
    )

    # Transform result for backward compatibility
    mcp_function_result = {
        "name": name,
        "individual_mcp_function_cache_cleared": result["individual_cache_cleared"],
        "mcp_function_list_cache_cleared": result["list_cache_cleared"],
        "cascaded_levels": result["cascaded_levels"],
        "total_child_caches_cleared": result["total_child_caches_cleared"],
        "total_individual_children_cleared": result.get(
            "total_individual_children_cleared", 0
        ),
        "errors": result["errors"],
    }

    return mcp_function_result


def purge_mcp_function_call_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    mcp_function_call_uuid: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    """
    MCP function call-specific wrapper for the universal cache purging function.

    Args:
        endpoint_id: The endpoint ID
        mcp_function_call_uuid: Function call UUID (for both individual and child cache clearing)
        cascade_depth: How many levels deep to cascade (default: 3)
        logger: logging.Logger instance

    Returns:
        Dict with comprehensive purge operation results
    """
    entity_keys = {}
    if mcp_function_call_uuid:
        entity_keys["mcp_function_call_uuid"] = mcp_function_call_uuid

    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_function_call",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys if entity_keys else None,
        cascade_depth=cascade_depth,
    )

    # Transform result for backward compatibility
    mcp_function_call_result = {
        "mcp_function_call_uuid": mcp_function_call_uuid,
        "individual_mcp_function_call_cache_cleared": result[
            "individual_cache_cleared"
        ],
        "mcp_function_call_list_cache_cleared": result["list_cache_cleared"],
        "cascaded_levels": result["cascaded_levels"],
        "total_child_caches_cleared": result["total_child_caches_cleared"],
        "total_individual_children_cleared": result.get(
            "total_individual_children_cleared", 0
        ),
        "errors": result["errors"],
    }

    return mcp_function_call_result


def purge_mcp_setting_cascading_cache(
    logger: logging.Logger,
    endpoint_id: str,
    setting_id: Optional[str] = None,
    cascade_depth: int = 3,
) -> Dict[str, Any]:
    """
    MCP setting-specific wrapper for the universal cache purging function.

    Args:
        endpoint_id: The endpoint ID
        setting_id: Setting ID (for both individual and child cache clearing)
        cascade_depth: How many levels deep to cascade (default: 3)
        logger: logging.Logger instance

    Returns:
        Dict with comprehensive purge operation results
    """
    entity_keys = {}
    if setting_id:
        entity_keys["setting_id"] = setting_id

    result = purge_entity_cascading_cache(
        logger,
        entity_type="mcp_setting",
        context_keys={"endpoint_id": endpoint_id} if endpoint_id else None,
        entity_keys=entity_keys if entity_keys else None,
        cascade_depth=cascade_depth,
    )

    # Transform result for backward compatibility
    mcp_setting_result = {
        "setting_id": setting_id,
        "individual_mcp_setting_cache_cleared": result["individual_cache_cleared"],
        "mcp_setting_list_cache_cleared": result["list_cache_cleared"],
        "cascaded_levels": result["cascaded_levels"],
        "total_child_caches_cleared": result["total_child_caches_cleared"],
        "total_individual_children_cleared": result.get(
            "total_individual_children_cleared", 0
        ),
        "errors": result["errors"],
    }

    return mcp_setting_result


__all__ = [
    "purge_entity_cascading_cache",
    "purge_mcp_module_cascading_cache",
    "purge_mcp_function_cascading_cache",
    "purge_mcp_function_call_cascading_cache",
    "purge_mcp_setting_cascading_cache",
]
