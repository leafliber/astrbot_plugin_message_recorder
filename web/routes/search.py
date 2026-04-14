"""搜索 API 路由"""

from quart import Blueprint, jsonify, request

from astrbot.api import logger

from ..utils import build_query_filter, format_message


def register_search_routes(bp: Blueprint, get_db):
    @bp.route("/api/search")
    async def api_search():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            keyword = request.args.get("keyword", "")
            if not keyword:
                return jsonify({"success": False, "error": "缺少关键词"}), 400

            query_filter = build_query_filter(request.args)
            query_filter.keyword = keyword

            messages = await get_db().query_messages(query_filter)
            total = await get_db().count_messages(query_filter)

            return jsonify({
                "success": True,
                "data": {
                    "messages": [format_message(msg) for msg in messages],
                    "pagination": {
                        "total": total,
                        "limit": query_filter.limit,
                        "offset": query_filter.offset,
                        "has_more": query_filter.offset + query_filter.limit < total
                    },
                    "keyword": keyword
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 搜索失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
