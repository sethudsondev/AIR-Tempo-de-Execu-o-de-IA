import time
import unittest

from tests.helpers import fresh_db
from sdc.world.state import WorldState


class TestWorldState(unittest.TestCase):
    def setUp(self):
        self.world = WorldState(fresh_db())

    def test_set_and_get_current(self):
        fact, outcome = self.world.set("project", "securedata-central", "status", "development")
        self.assertEqual(outcome, "created")
        self.assertEqual(self.world.get("project", "securedata-central", "status").value, "development")
        self.assertTrue(fact.is_current)

    def test_unchanged_is_noop(self):
        self.world.set("project", "sdc", "status", "development")
        fact, outcome = self.world.set("project", "sdc", "status", "development")
        self.assertEqual(outcome, "unchanged")
        self.assertEqual(fact.version, 1)

    def test_change_keeps_history(self):
        self.world.set("project", "sdc", "status", "development", source="briefing")
        time.sleep(0.01)
        fact, outcome = self.world.set("project", "sdc", "status", "production", source="deploy")
        self.assertEqual(outcome, "changed")
        self.assertEqual(fact.version, 2)

        current = self.world.get("project", "sdc", "status")
        self.assertEqual(current.value, "production")
        self.assertEqual(current.source, "deploy")

        prev = self.world.previous("project", "sdc", "status")
        self.assertEqual(prev.value, "development")
        self.assertIsNotNone(prev.valid_until)  # foi fechado
        self.assertEqual(prev.source, "briefing")

        hist = self.world.history("project", "sdc", "status")
        self.assertEqual([f.value for f in hist], ["development", "production"])
        self.assertLessEqual(hist[0].valid_until, hist[1].valid_from)

    def test_get_entity_all_attrs(self):
        self.world.set("service", "api", "status", "up")
        self.world.set("service", "api", "region", "sa-east-1")
        ent = self.world.get_entity("service", "api")
        self.assertEqual({k: v.value for k, v in ent.items()}, {"status": "up", "region": "sa-east-1"})

    def test_changed_since(self):
        t0 = time.time()
        time.sleep(0.01)
        self.world.set("service", "api", "status", "up")
        changes = self.world.changed_since(t0)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].attribute, "status")

    def test_only_one_current_row_per_attr(self):
        for v in ("a", "b", "c", "d"):
            self.world.set("e", "1", "attr", v)
        rows = self.world.db.query_all(
            "SELECT COUNT(*) c FROM world_state WHERE entity_type='e' AND entity_id='1' AND attribute='attr' AND valid_until IS NULL"
        )
        self.assertEqual(rows[0]["c"], 1)


if __name__ == "__main__":
    unittest.main()
