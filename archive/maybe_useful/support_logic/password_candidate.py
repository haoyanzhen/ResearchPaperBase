"""v1.0 — B-X01 bcrypt 候选，非认证系统；依赖可选第三方 bcrypt。"""
import re

import bcrypt

# 限定为该候选生成的格式和计算成本，拒绝未知/异常昂贵的外部散列。
_HASH = re.compile(rb"\$2b\$12\$[./A-Za-z0-9]{53}\Z")


def _password_bytes(plain: str) -> bytes:
    if not isinstance(plain, str):
        raise ValueError("password must be a string")
    raw = plain.encode("utf-8")
    if not 1 <= len(raw) <= 72 or b"\x00" in raw:
        raise ValueError("candidate accepts 1..72 UTF-8 bytes without NUL")
    return raw


def hash_candidate(plain: str) -> str:
    """每次随机 salt；不会归一化或截断输入。"""
    return bcrypt.hashpw(_password_bytes(plain), bcrypt.gensalt(rounds=12)).decode("ascii")


def matches_candidate(plain: str, encoded: str) -> bool:
    """非法密码/损坏/不支持的散列均不匹配；依赖故障不静默吞掉。"""
    try:
        raw = _password_bytes(plain)
        if not isinstance(encoded, str):
            return False
        hashed = encoded.encode("ascii")
        if not _HASH.fullmatch(hashed):
            return False
        return bcrypt.checkpw(raw, hashed)
    except (ValueError, UnicodeError):
        return False
