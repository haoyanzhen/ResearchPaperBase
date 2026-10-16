"""v1.0 — bcrypt 候选的离线验证；缺依赖明确跳过。"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import password_candidate as candidate
except ModuleNotFoundError as exc:
    if exc.name != "bcrypt":
        raise
    candidate = None


@unittest.skipIf(candidate is None, "optional bcrypt dependency unavailable")
class PasswordTest(unittest.TestCase):
    def test_chinese_wrong_password_and_salt(self):
        first = candidate.hash_candidate("中文 password")
        second = candidate.hash_candidate("中文 password")
        self.assertNotEqual(first, second)
        self.assertTrue(candidate.matches_candidate("中文 password", first))
        self.assertFalse(candidate.matches_candidate("wrong", first))

    def test_utf8_byte_boundary_no_silent_truncation(self):
        plain = "中" * 24
        hashed = candidate.hash_candidate(plain)
        self.assertTrue(candidate.matches_candidate(plain, hashed))
        for invalid in (plain + "a", "a" * 73, "", "a\x00b", None):
            with self.subTest(length=len(invalid) if invalid else 0):
                with self.assertRaises(ValueError):
                    candidate.hash_candidate(invalid)
                self.assertFalse(candidate.matches_candidate(invalid, hashed))

    def test_corrupt_and_unsupported_hashes(self):
        for hashed in (None, "", "中文", "$2b$12$broken", "$2b$31$" + "a" * 53):
            with self.subTest(hashed=hashed):
                self.assertFalse(candidate.matches_candidate("password", hashed))


if __name__ == "__main__":
    unittest.main()
