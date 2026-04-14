"""元数据 API 路由"""

from pathlib import Path
from quart import Blueprint, jsonify, request, send_file

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ...models import PLUGIN_DIR_NAME


def register_metadata_routes(bp: Blueprint, get_db):
    @bp.route("/api/platforms")
    async def api_platforms():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            platforms = await get_db().get_distinct_platforms()
            return jsonify({
                "success": True,
                "data": {"platforms": platforms}
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取平台列表失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/senders")
    async def api_senders():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")
            limit = int(request.args.get("limit", 50))

            senders = await get_db().get_distinct_senders(platform=platform, group_id=group_id, limit=limit)
            return jsonify({
                "success": True,
                "data": {"senders": senders}
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取发送者列表失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/groups")
    async def api_groups():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            platform = request.args.get("platform")
            limit = int(request.args.get("limit", 50))

            groups = await get_db().get_distinct_groups(platform=platform, limit=limit)
            return jsonify({
                "success": True,
                "data": {"groups": groups}
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取群组列表失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/media/<path:rel_path>")
    async def api_media(rel_path: str):
        media_base = Path(get_astrbot_plugin_data_path()) / PLUGIN_DIR_NAME / "media"
        file_path = media_base / rel_path

        resolved_base = media_base.resolve()
        resolved_path = file_path.resolve()

        try:
            resolved_path.relative_to(resolved_base)
        except ValueError:
            return jsonify({"success": False, "error": "非法路径"}), 403

        if not resolved_path.exists():
            return jsonify({"success": False, "error": "文件不存在"}), 404

        if not resolved_path.is_file():
            return jsonify({"success": False, "error": "非法路径"}), 403

        return await send_file(str(resolved_path))
