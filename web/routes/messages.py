"""消息查询 API 路由"""

from quart import Blueprint, jsonify, request

from astrbot.api import logger

from ..utils import build_query_filter, format_message, format_message_detail


def register_messages_routes(bp: Blueprint, get_db):
    @bp.route("/api/messages")
    async def api_messages():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            query_filter = build_query_filter(request.args)

            messages = await get_db().query_messages(query_filter)

            total = await get_db().count_messages(query_filter)

            formatted_messages = [format_message(msg) for msg in messages]

            return jsonify({
                "success": True,
                "data": {
                    "messages": formatted_messages,
                    "pagination": {
                        "total": total,
                        "limit": query_filter.limit,
                        "offset": query_filter.offset,
                        "has_more": query_filter.offset + query_filter.limit < total
                    }
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 查询消息失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/messages/<int:message_id>")
    async def api_message_detail(message_id: int):
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            message = await get_db().get_message_by_id(message_id)

            if not message:
                return jsonify({"success": False, "error": "消息不存在"}), 404

            return jsonify({
                "success": True,
                "data": format_message_detail(message)
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取消息详情失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/messages/<int:message_id>/context")
    async def api_message_context(message_id: int):
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            before = int(request.args.get("before", 5))
            after = int(request.args.get("after", 5))

            context = await get_db().get_context_messages(message_id, before, after)

            return jsonify({
                "success": True,
                "data": {
                    "target": format_message_detail(await get_db().get_message_by_id(message_id)),
                    "before": [format_message(m) for m in context["before"]],
                    "after": [format_message(m) for m in context["after"]]
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取消息上下文失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
