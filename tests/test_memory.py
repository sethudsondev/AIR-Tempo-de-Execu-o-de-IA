import time
import unittest

from tests.helpers import fresh_db
from sdc.core.types import Importance, MemoryStatus
from sdc.memory.store import MemoryStore


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(fresh_db())

    def test_create_and_get(self):
        mem, outcome = self.store.store("project.name", "SecureData Central", type="project_information", importance="high")
        self.assertEqual(outcome, "created")
        got = self.store.get(mem.id)
        self.assertEqual(got.content, "SecureData Central")
        self.assertEqual(got.importance, Importance.HIGH)
        self.assertEqual(got.version, 1)

    def test_dedup_same_content(self):
        a, _ = self.store.store("k", "v")
        b, outcome = self.store.store("k", "v")
        self.assertEqual(outcome, "deduped")
        self.assertEqual(a.id, b.id)

    def test_supersede_on_change(self):
        a, _ = self.store.store("k", "v1")
        time.sleep(0.01)
        b, outcome = self.store.store("k", "v2")
        self.assertEqual(outcome, "superseded")
        self.assertNotEqual(a.id, b.id)
        self.assertEqual(b.version, 2)
        self.assertEqual(b.supersedes, a.id)
        self.assertEqual(self.store.get(a.id).status, MemoryStatus.SUPERSEDED)
        self.assertEqual(self.store.get_by_key("k").content, "v2")

    def test_only_one_active_per_key(self):
        self.store.store("k", "v1")
        self.store.store("k", "v2")
        self.store.store("k", "v3")
        actives = [m for m in self.store.all_active() if m.key == "k"]
        self.assertEqual(len(actives), 1)

    def test_update_creates_version(self):
        a, _ = self.store.store("k", "v1")
        b, outcome = self.store.update(a.id, content="v2")
        self.assertEqual(outcome, "superseded")
        self.assertEqual(b.version, 2)

    def test_update_missing_returns_none(self):
        self.assertIsNone(self.store.update("nope", content="x"))

    def test_soft_delete(self):
        a, _ = self.store.store("k", "v1")
        self.assertTrue(self.store.delete(a.id))
        self.assertEqual(self.store.get(a.id).status, MemoryStatus.DELETED)
        self.assertIsNone(self.store.get_by_key("k"))
        self.assertFalse(self.store.delete(a.id))  # segunda vez: nada a fazer

    def test_history(self):
        self.store.store("k", "v1")
        self.store.store("k", "v2")
        self.store.store("k", "v3")
        hist = self.store.history("k")
        self.assertEqual([m.version for m in hist], [1, 2, 3])
        self.assertEqual([m.content for m in hist], ["v1", "v2", "v3"])

    def test_search_keyword_and_ranking(self):
        self.store.store("project.name", "SecureData Central", type="project_information", importance="critical")
        self.store.store("user.tone", "formal", type="preference")
        self.store.store("random.note", "algo sobre bananas", type="note")
        results = self.store.search("securedata central", limit=5)
        self.assertTrue(results)
        self.assertIn("SecureData", results[0][0].content)
        self.assertGreater(results[0][1], 0)

    def test_project_isolation(self):
        self.store.store("k", "global-val")
        self.store.store("k", "proj-val", project="alpha")
        self.assertEqual(self.store.get_by_key("k", "alpha").content, "proj-val")
        self.assertEqual(self.store.get_by_key("k", "").content, "global-val")
        # busca no projeto alpha ve o dele + globais
        keys = {m.key for m in self.store.all_active(project="alpha")}
        self.assertIn("k", keys)


if __name__ == "__main__":
    unittest.main()
