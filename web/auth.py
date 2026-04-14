"""认证模块：验证码和 Token 管理"""

import time
import uuid
import secrets
import hashlib
import string
from typing import Dict, Any

from astrbot.api import logger

from .constants import CAPTCHA_LENGTH, CAPTCHA_EXPIRE_SECONDS, AUTH_TOKEN_EXPIRE_SECONDS
from .storage import get_captcha_store, get_auth_tokens


def _generate_captcha_code(length: int = CAPTCHA_LENGTH) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def _generate_captcha_id() -> str:
    return uuid.uuid4().hex[:16]


def _generate_auth_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_captcha() -> str:
    captcha_id = _generate_captcha_id()
    code = _generate_captcha_code()
    get_captcha_store()[captcha_id] = {
        "code": code,
        "created_at": time.time(),
    }
    logger.info(f"[MessageRecorder Web] 验证码: {code} (ID: {captcha_id})")
    return captcha_id


def verify_captcha(captcha_id: str, code: str) -> bool:
    captcha_store = get_captcha_store()
    captcha = captcha_store.get(captcha_id)
    if not captcha:
        return False

    if time.time() - captcha["created_at"] > CAPTCHA_EXPIRE_SECONDS:
        captcha_store.pop(captcha_id, None)
        return False

    if captcha["code"] != code:
        return False

    captcha_store.pop(captcha_id, None)
    return True


def create_auth_token() -> str:
    token = _generate_auth_token()
    token_hash = _hash_token(token)
    get_auth_tokens()[token_hash] = {
        "created_at": time.time(),
    }
    return token


def verify_auth_token(token: str) -> bool:
    if not token:
        return False

    auth_tokens = get_auth_tokens()
    token_hash = _hash_token(token)
    auth = auth_tokens.get(token_hash)

    if not auth:
        return False

    if time.time() - auth["created_at"] > AUTH_TOKEN_EXPIRE_SECONDS:
        auth_tokens.pop(token_hash, None)
        return False

    return True


def cleanup_expired_captchas_and_tokens():
    current_time = time.time()
    captcha_store = get_captcha_store()
    auth_tokens = get_auth_tokens()

    expired_captchas = [
        cid for cid, c in captcha_store.items()
        if current_time - c["created_at"] > CAPTCHA_EXPIRE_SECONDS
    ]
    for cid in expired_captchas:
        captcha_store.pop(cid, None)

    expired_tokens = [
        th for th, a in auth_tokens.items()
        if current_time - a["created_at"] > AUTH_TOKEN_EXPIRE_SECONDS
    ]
    for th in expired_tokens:
        auth_tokens.pop(th, None)
