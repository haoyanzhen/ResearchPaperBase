from nanoid import generate

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_SIZE = 12


def new_id(prefix: str) -> str:
    """生成带前缀的短 ID，如 u_x3k9mz1abcde"""
    return f"{prefix}_{generate(_ALPHABET, _SIZE)}"
