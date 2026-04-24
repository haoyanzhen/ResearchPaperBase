"""
单元测试：app.utils.ids（qa_design §7）

覆盖：
  - new_id() 前缀格式
  - new_id() 生成 ID 唯一性
  - new_id() 字符集约束（只含字母数字和下划线）
"""

import re
import pytest
from app.utils.ids import new_id


class TestNewId:
    def test_prefix_format(self):
        uid = new_id("u")
        assert uid.startswith("u_")

    def test_multi_char_prefix(self):
        sid = new_id("sr")
        assert sid.startswith("sr_")

    def test_length(self):
        """前缀 + '_' + 12 字符 nanoid。"""
        uid = new_id("u")
        # "u_" + 12 chars = 14
        assert len(uid) == 2 + 12

        sid = new_id("sr")
        assert len(sid) == 3 + 12

    def test_charset(self):
        """只包含 [0-9a-z_]。"""
        for prefix in ("u", "proj", "sr", "kw"):
            uid = new_id(prefix)
            assert re.fullmatch(r"[0-9a-z_]+", uid), f"Invalid chars in {uid}"

    def test_uniqueness(self):
        ids = {new_id("proj") for _ in range(500)}
        assert len(ids) == 500

    def test_different_prefixes_dont_collide(self):
        u_ids = {new_id("u") for _ in range(100)}
        proj_ids = {new_id("proj") for _ in range(100)}
        assert u_ids.isdisjoint(proj_ids)
