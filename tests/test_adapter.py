import unittest

from tests.helpers import fresh_db
from sdc.config import Config
from sdc.mcp.adapter import Adapter


def make_adapter():
    cfg = Config()
    cfg.db_path = ":memory:"
    return Adapter(cfg, db=fresh_db())


class TestAdapterMemory(unittest.TestCase):
    def setUp(self):
        self.a = make_adapter()

    def test_store_get_update_delete_flow(self):
        r = self.a.store_memory("project.name", "SecureData Central", type="project_information", importance="high")
        self.assertTrue(r["ok"])
        self.assertEqual(r["outcome"], "created")
        mid = r["memory"]["id"]

        g = self.a.get_memory(id=mid)
        self.assertEqual(g["memory"]["content"], "SecureData Central")

        g2 = self.a.get_memory(key="project.name")
        self.assertEqual(g2["memory"]["id"], mid)

        u = self.a.update_memory(mid, content="SecureData Central v2")
        self.assertTrue(u["ok"])
        self.assertEqual(u["memory"]["version"], 2)

        d = self.a.delete_memory(u["memory"]["id"])
        self.assertTrue(d["ok"])
        self.assertFalse(self.a.get_memory(key="project.name")["ok"])

    def test_dedup(self):
        self.a.store_memory("k", "v")
        r = self.a.store_memory("k", "v")
        self.assertEqual(r["outcome"], "deduped")

    def test_validation_errors_are_structured(self):
        r = self.a.store_memory("", "conteudo")
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "validation")

        r2 = self.a.store_memory("bad key!!", "x")
        self.assertFalse(r2["ok"])

        r3 = self.a.store_memory("k", "x", metadata="{not json")
        self.assertFalse(r3["ok"])

    def test_search_and_history(self):
        self.a.store_memory("project.name", "SecureData Central", importance="critical")
        self.a.update_memory(self.a.get_memory(key="project.name")["memory"]["id"], content="SecureData Central 2")
        s = self.a.search_memory("securedata central")
        self.assertGreaterEqual(s["count"], 1)
        h = self.a.memory_history("project.name")
        self.assertEqual(h["count"], 2)

    def test_missing_returns_not_found(self):
        self.assertEqual(self.a.get_memory(id="nope")["code"], "not_found")
        self.assertEqual(self.a.update_memory("nope", content="x")["code"], "not_found")
        self.assertEqual(self.a.delete_memory("nope")["code"], "not_found")


class TestAdapterWorld(unittest.TestCase):
    def setUp(self):
        self.a = make_adapter()

    def test_state_change_and_history(self):
        r1 = self.a.update_world_state("project", "sdc", "status", "development", source="briefing")
        self.assertEqual(r1["outcome"], "created")

        r2 = self.a.update_world_state("project", "sdc", "status", "production", source="deploy")
        self.assertEqual(r2["outcome"], "changed")
        self.assertEqual(r2["fact"]["value"], "production")
        self.assertEqual(r2["previous"]["value"], "development")

        cur = self.a.get_world_state("project", "sdc", "status")
        self.assertEqual(cur["current"]["value"], "production")
        self.assertEqual(cur["previous"]["value"], "development")

        hist = self.a.world_history("project", "sdc", "status")
        self.assertEqual([f["value"] for f in hist["history"]], ["development", "production"])

    def test_get_full_entity(self):
        self.a.update_world_state("service", "api", "status", "up")
        self.a.update_world_state("service", "api", "region", "sa-east-1")
        st = self.a.get_world_state("service", "api")
        self.assertEqual(set(st["state"]), {"status", "region"})

    def test_unchanged(self):
        self.a.update_world_state("e", "1", "a", "v")
        r = self.a.update_world_state("e", "1", "a", "v")
        self.assertEqual(r["outcome"], "unchanged")


class TestAdapterEventsContext(unittest.TestCase):
    def setUp(self):
        self.a = make_adapter()

    def test_events_recorded_on_writes(self):
        self.a.store_memory("k", "v1")
        self.a.update_world_state("p", "x", "status", "dev")
        rc = self.a.recent_changes(limit=10)
        types = {e["event_type"] for e in rc["events"]}
        self.assertIn("memory.created", types)
        self.assertIn("world.changed", types)

    def test_manual_event(self):
        r = self.a.record_event("deploy", entity_id="project:sdc", payload={"version": "1.0.0"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.a.recent_changes(event_type="deploy")["count"], 1)

    def test_get_context_budget_and_refs(self):
        self.a.store_memory("project.name", "SecureData Central", importance="critical")
        self.a.update_world_state("project", "securedata", "status", "development")
        r = self.a.get_context("nome e status do projeto SecureData", max_tokens=500, session_id="s1")
        self.assertTrue(r["ok"])
        self.assertIn("SecureData", r["context"])
        self.assertLessEqual(r["tokens_used"], 500)
        self.assertTrue(r["references"])
        self.assertIn(r["token_method"], ("heuristic_chars_div_4", "tiktoken:cl100k_base"))

    def test_search_context(self):
        self.a.store_memory("user.tone", "formal", type="preference")
        r = self.a.search_context("tom de resposta preferido")
        self.assertTrue(r["ok"])

    def test_status_no_secrets(self):
        r = self.a.status()
        self.assertTrue(r["ok"])
        blob = repr(r).lower()
        for bad in ("password", "secret", "api_key", "token="):
            self.assertNotIn(bad, blob)


if __name__ == "__main__":
    unittest.main()
