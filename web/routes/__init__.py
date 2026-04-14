"""路由模块"""

from .stats import register_stats_routes
from .messages import register_messages_routes
from .search import register_search_routes
from .export import register_export_routes
from .import_routes import register_import_routes
from .captcha import register_captcha_routes
from .metadata import register_metadata_routes

__all__ = [
    "register_stats_routes",
    "register_messages_routes",
    "register_search_routes",
    "register_export_routes",
    "register_import_routes",
    "register_captcha_routes",
    "register_metadata_routes",
]
