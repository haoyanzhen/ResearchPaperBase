"""v1.0 — 仅离线标准库测试；不加载旧项目、环境配置或数据库。"""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import helpers


class HelpersTest(unittest.TestCase):
    def test_nested_copy_and_exception_restore(self):
        self.assertEqual(helpers.context_snapshot(), {})
        with helpers.scoped_context(trace_id="parent"):
            copied = helpers.context_snapshot()
            copied["trace_id"] = "changed"
            self.assertEqual(helpers.context_snapshot()["trace_id"], "parent")
            with self.assertRaises(RuntimeError):
                with helpers.scoped_context(trace_id="child", operation_id="op"):
                    self.assertEqual(helpers.context_snapshot()["trace_id"], "child")
                    raise RuntimeError("scope exits")
            self.assertEqual(helpers.context_snapshot(), {"trace_id": "parent"})
        self.assertEqual(helpers.context_snapshot(), {})

    def test_reject_uncontrolled_fields(self):
        for fields in ({"password": "secret"}, {"trace_id": []},
                       {"trace_id": "line\nbreak"}, {"trace_id": "a" * 129}):
            with self.subTest(fields=list(fields)), self.assertRaises(ValueError):
                with helpers.scoped_context(**fields):
                    self.fail("invalid context accepted")
        self.assertEqual(helpers.context_snapshot(), {})

    def test_random_identifier_contract(self):
        with patch.object(helpers.secrets, "token_hex", return_value="a" * 32) as random:
            self.assertEqual(helpers.random_identifier("asset"), "asset_" + "a" * 32)
            random.assert_called_once_with(16)
        for prefix in ("", "a_", "A", "a" * 17, None):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                helpers.random_identifier(prefix)

    def test_quote_identifier(self):
        self.assertEqual(helpers.quote_identifier('a"; DROP TABLE x;--'), '"a""; DROP TABLE x;--"')
        self.assertEqual(helpers.quote_identifier("数据"), '"数据"')
        self.assertEqual(helpers.quote_identifier("a.b"), '"a.b"')
        self.assertEqual(helpers.quote_identifier("数" * 21), '"' + "数" * 21 + '"')
        for value in (None, "", "a\x00b", "a" * 64, "数" * 22):
            with self.subTest(value=value), self.assertRaises(ValueError):
                helpers.quote_identifier(value)


class ContextAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_tasks_inherit_then_isolate(self):
        async def child(name):
            self.assertEqual(helpers.context_snapshot(), {"trace_id": "parent"})
            with helpers.scoped_context(trace_id=name):
                await asyncio.sleep(0)
                return helpers.context_snapshot()
        with helpers.scoped_context(trace_id="parent"):
            result = await asyncio.gather(child("one"), child("two"))
            self.assertEqual(result, [{"trace_id": "one"}, {"trace_id": "two"}])
            self.assertEqual(helpers.context_snapshot(), {"trace_id": "parent"})


if __name__ == "__main__":
    unittest.main()
