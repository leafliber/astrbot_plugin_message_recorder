"""统计 API 路由"""

from quart import Blueprint, jsonify, request

from astrbot.api import logger

from ...time_utils import parse_time_range
from ..utils import format_timestamp


def register_stats_routes(bp: Blueprint, get_db):
    @bp.route("/api/stats")
    async def api_stats():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            stats = await get_db().get_stats()

            time_range = {}
            if stats.oldest_timestamp:
                time_range["start"] = format_timestamp(stats.oldest_timestamp)
            if stats.newest_timestamp:
                time_range["end"] = format_timestamp(stats.newest_timestamp)

            return jsonify({
                "success": True,
                "data": {
                    "total_count": stats.total_count,
                    "group_message_count": stats.group_message_count,
                    "private_message_count": stats.private_message_count,
                    "platform_stats": stats.platform_stats,
                    "platform_count": len(stats.platform_stats),
                    "oldest_timestamp": stats.oldest_timestamp,
                    "newest_timestamp": stats.newest_timestamp,
                    "time_range": time_range
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取统计失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/stats/timeline")
    async def api_stats_timeline():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            interval = request.args.get("interval", "day")
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")
            start_time = request.args.get("start_time")
            end_time = request.args.get("end_time")

            start_ts = int(start_time) if start_time else None
            end_ts = int(end_time) if end_time else None

            points = await get_db().get_timeline_stats(
                interval=interval,
                start_time=start_ts,
                end_time=end_ts,
                platform=platform,
                group_id=group_id
            )

            return jsonify({
                "success": True,
                "data": {
                    "interval": interval,
                    "points": points,
                    "total_points": len(points)
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取时间趋势失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/stats/senders")
    async def api_stats_senders():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            limit = int(request.args.get("limit", 20))
            time_range = request.args.get("time")
            platform = request.args.get("platform")
            group_id = request.args.get("group_id")

            start_time, end_time = None, None
            if time_range:
                start_time, end_time = parse_time_range(time_range)

            senders = await get_db().get_sender_ranking(
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                platform=platform,
                group_id=group_id
            )

            return jsonify({
                "success": True,
                "data": {
                    "senders": senders,
                    "total": len(senders)
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取发送者排行失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/stats/groups")
    async def api_stats_groups():
        if not get_db():
            return jsonify({"success": False, "error": "数据库未初始化"}), 500

        try:
            limit = int(request.args.get("limit", 20))
            time_range = request.args.get("time")
            platform = request.args.get("platform")

            start_time, end_time = None, None
            if time_range:
                start_time, end_time = parse_time_range(time_range)

            groups = await get_db().get_group_ranking(
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                platform=platform
            )

            return jsonify({
                "success": True,
                "data": {
                    "groups": groups,
                    "total": len(groups)
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 获取群组统计失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
