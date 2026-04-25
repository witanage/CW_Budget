"""
Settings Service

Manages application-wide settings and configuration:
- UI settings (modal opacity, themes)
- Upload modes and preferences
- Template context variables
"""

import logging

from db import get_setting

logger = logging.getLogger(__name__)


def get_upload_mode():
    """
    Get the bill upload mode setting.
    
    Returns:
        String: 'sequential' or 'batch'
        Default: 'sequential'
    """
    mode = get_setting('bill_upload_mode', 'sequential')
    logger.info(f"Upload mode requested: returning '{mode}'")
    return mode


def get_modal_opacity():
    """
    Get the modal background opacity setting.
    
    Returns:
        String: Float value between '0.10' and '1.00'
        Default: '0.85'
    """
    raw = get_setting('modal_opacity', '0.85') or '0.85'
    try:
        val = float(raw)
        if val < 0.1:
            val = 0.1
        elif val > 1.0:
            val = 1.0
        modal_opacity = f"{val:.2f}"
    except (TypeError, ValueError):
        logger.warning(f"Invalid modal_opacity value: {raw}, using default")
        modal_opacity = '0.85'
    
    return modal_opacity


def get_global_template_vars():
    """
    Get all global template variables for Flask context processor.
    
    Returns:
        Dictionary of template variables to inject into all templates
    """
    return {
        'modal_opacity': get_modal_opacity()
    }


def update_setting(key, value):
    """
    Update a setting value (wrapper for future enhancement).
    
    Args:
        key: Setting key
        value: New value
    
    Returns:
        Boolean indicating success
    
    Note: Currently settings are managed via admin routes.
    This is a placeholder for future direct setting updates.
    """
    logger.info(f"Setting update requested: {key} = {value}")
    # Future implementation: direct database update
    # For now, settings are updated via admin_service
    return True
