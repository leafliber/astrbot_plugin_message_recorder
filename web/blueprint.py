"""Quart Blueprint 定义 - 主入口模块

本模块负责创建和配置 Quart Blueprint，整合所有路由模块。
各功能模块已拆分到独立文件中：
- constants.py: 配置常量
- storage.py: 全局存储管理
- auth.py: 认证模块（验证码、Token）
- utils.py: 辅助函数
- export_task.py: 导出任务执行
- import_task.py: 导入任务执行
- routes/: API 路由模块
"""

from quart import Blueprint, jsonify, request, render_template

from astrbot.api import logger

from .auth import verify_auth_token
from .utils import get_plugin_dir, cleanup_temp_dir
from .export_task import cleanup_expired_export_files
from .routes import (
    register_stats_routes,
    register_messages_routes,
    register_search_routes,
    register_export_routes,
    register_import_routes,
    register_captcha_routes,
    register_metadata_routes,
)


_WRITE_ENDPOINT_PREFIXES = ("/api/import",)


def create_blueprint(plugin_instance) -> Blueprint:
    plugin_dir = get_plugin_dir()

    logger.info(f"[MessageRecorder Web] 插件目录: {plugin_dir}")

    cleanup_temp_dir()

    bp = Blueprint(
        "message_recorder_web",
        __name__,
        template_folder=str(plugin_dir / "templates"),
        static_folder=str(plugin_dir / "static"),
        static_url_path="/static"
    )

    def get_db():
        return plugin_instance._db

    @bp.before_request
    async def check_write_auth():
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return None
        if not any(request.path.startswith(prefix) for prefix in _WRITE_ENDPOINT_PREFIXES):
            return None

        if request.path in ("/api/captcha", "/api/captcha/verify"):
            return None

        token = request.headers.get("X-Auth-Token", "") or request.args.get("auth_token", "")
        if not verify_auth_token(token):
            return jsonify({
                "success": False,
                "error": "需要验证码鉴权",
                "require_captcha": True
            }), 401

    @bp.route("/")
    async def index():
        try:
            return await render_template("index.html")
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 渲染主页模板失败: {e}")
            return f"<h1>模板渲染错误</h1><p>{str(e)}</p><p>模板目录: {bp.template_folder}</p>", 500

    @bp.route("/search")
    async def search_page():
        return await render_template("search.html")

    @bp.route("/export")
    async def export_page():
        return await render_template("export.html")

    @bp.route("/import")
    async def import_page():
        return await render_template("import.html")

    register_stats_routes(bp, get_db)
    register_messages_routes(bp, get_db)
    register_search_routes(bp, get_db)
    register_export_routes(bp, get_db)
    register_import_routes(bp, get_db)
    register_captcha_routes(bp, get_db)
    register_metadata_routes(bp, get_db)

    return bp
