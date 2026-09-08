import time
import unittest

from tests.helpers import fresh_db
from sdc.events.log import EventLog


class TestEventLog(unittest.TestCase):
    def setUp(self):
        self.log = EventLog(fresh_db())

    def test_record_and_recent(self):
        self.log.record("memory.created", entity_id="mem_1", payload={"key": "project.name"})
        self.log.record("world.changed", entity_id="project:sdc", payload={"attr": "status"})
        recent = self.log.recent(limit=10)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0].event_type, "world.changed")  # mais novo primeiro

    def test_filter_by_type(self):
        self.log.record("deploy")
        self.log.record("memory.created")
        self.log.record("deploy")
        self.assertEqual(len(self.log.recent(event_type="deploy")), 2)

    def test_filter_since(self):
        t0 = time.time()
        time.sleep(0.01)
        self.log.record("x")
        self.assertEqual(len(self.log.recent(since_ts=t0)), 1)
        self.assertEqual(len(self.log.recent(since_ts=time.time() + 1)), 0)

    def test_project_scope(self):
        self.log.record("x", project="alpha")
        self.log.record("y")  # global
        self.log.record("z", project="beta")
        got = {e.event_type for e in self.log.recent(project="alpha")}
        self.assertEqual(got, {"x", "y"})


if __name__ == "__main__":
    unittest.main()
