import unittest

from tests.helpers import fresh_db
from sdc.context.engine import ContextEngine
from sdc.context.retrieval import Retriever
from sdc.events.log import EventLog
from sdc.memory.store import MemoryStore
from sdc.world.state import WorldState


def build_engine(db, max_tokens=2000):
    mem = MemoryStore(db)
    world = WorldState(db)
    events = EventLog(db)
    retr = Retriever(mem, world, events, enable_semantic=False)
    return ContextEngine(db, retr, max_context_tokens=max_tokens), mem, world, events


class TestHandles(unittest.TestCase):
    def test_put_get_render_summary(self):
        eng, *_ = build_engine(fresh_db())
        big = "linha " * 500
        hid = eng.put(big, kind="tool_output", label="ls -R")
        self.assertEqual(eng.get(hid), big)
        rendered = eng.handles.render([hid])
        self.assertLess(len(rendered), len(big))
        self.assertIn("get(", rendered)

    def test_small_content_inlined(self):
        eng, *_ = build_engine(fresh_db())
        hid = eng.put("curto", kind="note", label="x")
        self.assertEqual(eng.handles.render([hid]), "curto")


class TestContextBuild(unittest.TestCase):
    def test_relevant_only(self):
        eng, mem, world, events = build_engine(fresh_db())
        mem.store("project.name", "SecureData Central", type="project_information", importance="critical")
        mem.store("user.tone", "formal", type="preference")
        mem.store("unrelated", "receita de bolo de cenoura", type="note")
        res = eng.build("qual o nome do projeto")
        self.assertTrue(res.text)
        self.assertIn("SecureData", res.text)
        self.assertNotIn("cenoura", res.text)

    def test_respects_token_budget(self):
        eng, mem, world, events = build_engine(fresh_db(), max_tokens=40)
        for i in range(30):
            mem.store(f"note.{i}", f"conteudo importante numero {i} " * 20, importance="high")
        res = eng.build("conteudo importante", max_tokens=40)
        self.assertLessEqual(res.tokens_used, 40)
        self.assertGreater(res.dropped_for_budget, 0)

    def test_priority_importance(self):
        eng, mem, world, events = build_engine(fresh_db(), max_tokens=30)
        mem.store("a.low", "alpha beta gamma", importance="low")
        mem.store("a.crit", "alpha beta gamma", importance="critical")
        res = eng.build("alpha beta gamma", max_tokens=30)
        self.assertIn("a.crit", res.text)

    def test_world_state_enters_context(self):
        eng, mem, world, events = build_engine(fresh_db())
        world.set("project", "sdc", "status", "development")
        res = eng.build("status do projeto sdc")
        self.assertIn("development", res.text)

    def test_records_context_refs(self):
        db = fresh_db()
        eng, mem, world, events = build_engine(db)
        m, _ = mem.store("project.name", "SecureData Central", importance="high")
        eng.build("nome do projeto", session_id="s1")
        rows = db.query_all("SELECT * FROM context_refs WHERE session_id='s1'")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["memory_id"], m.id)

    def test_no_redundancy_same_ref_once(self):
        eng, mem, world, events = build_engine(fresh_db())
        mem.store("k", "valor unico repetido", importance="high")
        res = eng.build("valor unico repetido")
        ids = [r["id"] for r in res.references]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
