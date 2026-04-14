"""验证码 API 路由"""

from quart import Blueprint, jsonify, request

from astrbot.api import logger

from ..auth import create_captcha, verify_captcha, create_auth_token


def register_captcha_routes(bp: Blueprint, get_db):
    @bp.route("/api/captcha")
    async def api_captcha():
        try:
            captcha_id = create_captcha()
            return jsonify({
                "success": True,
                "data": {
                    "captcha_id": captcha_id
                }
            })
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 生成验证码失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @bp.route("/api/captcha/verify", methods=["POST"])
    async def api_captcha_verify():
        try:
            data = await request.get_json()
            captcha_id = data.get("captcha_id", "")
            code = data.get("code", "")

            if not captcha_id or not code:
                return jsonify({
                    "success": False,
                    "error": "缺少验证码参数"
                }), 400

            if verify_captcha(captcha_id, code):
                token = create_auth_token()
                return jsonify({
                    "success": True,
                    "data": {
                        "auth_token": token
                    }
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "验证码错误或已过期"
                }), 400
        except Exception as e:
            logger.error(f"[MessageRecorder Web] 验证验证码失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
