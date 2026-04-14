"""全局存储管理"""

from typing import Dict, Any


_captcha_store: Dict[str, Dict[str, Any]] = {}

_auth_tokens: Dict[str, Dict[str, Any]] = {}

_export_tasks: Dict[str, Dict[str, Any]] = {}

_chunk_sessions: Dict[str, Dict[str, Any]] = {}

_import_tasks: Dict[str, Dict[str, Any]] = {}


def get_captcha_store() -> Dict[str, Dict[str, Any]]:
    return _captcha_store


def get_auth_tokens() -> Dict[str, Dict[str, Any]]:
    return _auth_tokens


def get_export_tasks() -> Dict[str, Dict[str, Any]]:
    return _export_tasks


def get_chunk_sessions() -> Dict[str, Dict[str, Any]]:
    return _chunk_sessions


def get_import_tasks() -> Dict[str, Dict[str, Any]]:
    return _import_tasks
