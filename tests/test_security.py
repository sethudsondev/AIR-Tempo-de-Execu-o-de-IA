"""Seguranca: validacao de input, limites, SQL injection, sem secrets."""
import unittest

from tests.helpers import fresh_db
from sdc.config import Config
from sdc.mcp.adapter import Adapter
from sdc.security.guard import (
    ValidationError, clamp_limit, clean_key, clean_metadata, clean_text,
)


def make_adapter(**over):
    cfg = Config()
    cfg.db_path = ":memory:"
    for k, v in over.items():
        setattr(cfg, k, v)
    return Adapter(cfg, db=fresh_db())


class TestGuard(unittest.TestCase):
    def test_content_length_limit(self):
        with self.assertRaises(ValidationError):
            clean_text("x" * 50, field="content", max_chars=10)

    def test_empty_required(self):
        with self.assertRaises(ValidationError):
            clean_text("   ", field="content", max_chars=100)
        self.assertEqual(clean_text("", field="x", max_chars=100, allow_empty=True), "")

    def test_control_chars_stripped(self):
        self.assertEqual(clean_text("a\x00b\x07c", field="x", max_chars=100), "abc")

    def test_key_charset(self):
        clean_key("project.name", max_chars=100)
        clean_key("user_tone:v2", max_chars=100)
        with self.assertRaises(ValidationError):
            clean_key("drop table; --", max_chars=100)
        with self.assertRaises(ValidationError):
            clean_key("has spaces and !!!", max_chars=100)

    def test_metadata_must_be_json_object(self):
        self.assertEqual(clean_metadata(None, max_bytes=1000), {})
        self.assertEqual(clean_metadata('{"a":1}', max_bytes=1000), {"a": 1})
        with self.assertRaises(ValidationError):
            clean_metadata("[1,2,3]", max_bytes=1000)
        with self.assertRaises(ValidationError):
            clean_metadata("{bad", max_bytes=1000)

    def test_metadata_size_limit(self):
        with self.assertRaises(ValidationError):
            clean_metadata({"big": "x" * 5000}, max_bytes=1000)

    def test_clamp_limit(self):
        self.assertEqual(clamp_limit(None, default=5, maximum=50), 5)
        self.assertEqual(clamp_limit(999, default=5, maximum=50), 50)
        self.assertEqual(clamp_limit(-3, default=5, maximum=50), 1)
        self.assertEqual(clamp_limit("abc", default=5, maximum=50), 5)


class TestAdapterSecurity(unittest.TestCase):
    def test_sql_injection_is_data_not_code(self):
        a = make_adapter()
        payload = "Robert'); DROP TABLE memories; --"
        r = a.store_memory("attack.attempt", payload)
        self.assertTrue(r["ok"])
        # tabela intacta e o payload gravado literalmente
        self.assertEqual(a.get_memory(key="attack.attempt")["memory"]["content"], payload)
        self.assertTrue(a.status()["ok"])

    def test_injection_via_key_rejected(self):
        a = make_adapter()
        r = a.store_memory("'; DROP TABLE memories; --", "x")
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "validation")

    def test_content_over_limit_rejected(self):
        a = make_adapter(max_content_chars=100)
        r = a.store_memory("k", "z" * 500)
        self.assertFalse(r["ok"])

    def test_query_over_limit_rejected(self):
        a = make_adapter(max_query_chars=20)
        r = a.search_memory("q" * 200)
        self.assertFalse(r["ok"])

    def test_metadata_bomb_rejected(self):
        a = make_adapter(max_metadata_bytes=200)
        r = a.store_memory("k", "v", metadata={"x": "y" * 1000})
        self.assertFalse(r["ok"])

    def test_no_secret_like_fields_in_status(self):
        a = make_adapter()
        blob = repr(a.status()).lower()
        for bad in ("password", "secret", "api_key", "apikey", "authorization", "bearer"):
            self.assertNotIn(bad, blob)

    def test_errors_never_leak_stacktrace(self):
        a = make_adapter()
        r = a.get_world_state("bad type!!", "x", "y")
        self.assertFalse(r["ok"])
        self.assertNotIn("Traceback", str(r))
        self.assertNotIn("sqlite3", str(r).lower())

    def test_limit_is_clamped_not_trusted(self):
        a = make_adapter(max_search_limit=10)
        for i in range(20):
            a.store_memory(f"k{i}", "conteudo alpha comum")
        r = a.search_memory("alpha", limit=9999)
        self.assertLessEqual(r["count"], 10)


if __name__ == "__main__":
    unittest.main()
