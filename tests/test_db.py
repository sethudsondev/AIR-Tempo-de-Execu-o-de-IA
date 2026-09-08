import unittest

from tests.helpers import fresh_db
from sdc.db.migrations import MIGRATIONS, current_version, run_migrations


class TestDatabase(unittest.TestCase):
    def test_migrations_apply_and_are_idempotent(self):
        db = fresh_db()
        self.assertEqual(current_version(db.conn), max(m[0] for m in MIGRATIONS))
        # rodar de novo nao aplica nada
        applied = run_migrations(db.conn)
        self.assertEqual(applied, [])

    def test_tables_exist(self):
        db = fresh_db()
        rows = db.query_all("SELECT name FROM sqlite_master WHERE type='table'")
        names = {r["name"] for r in rows}
        for t in ("memories", "world_state", "context_refs", "events", "schema_migrations"):
            self.assertIn(t, names)

    def test_foreign_keys_on(self):
        db = fresh_db()
        self.assertEqual(db.query_one("PRAGMA foreign_keys")[0], 1)

    def test_parameterized_queries_are_safe(self):
        db = fresh_db()
        nasty = "x'; DROP TABLE memories; --"
        db.execute(
            "INSERT INTO memories (id,key,content,type,source,importance,project,status,version,supersedes,created_at,updated_at,metadata)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("m1", nasty, "c", "note", "t", "low", "", "active", 1, None, 1.0, 1.0, "{}"),
        )
        rows = db.query_all("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")
        self.assertEqual(len(rows), 1)  # tabela ainda existe
        self.assertEqual(db.query_one("SELECT key FROM memories WHERE id='m1'")[0], nasty)


if __name__ == "__main__":
    unittest.main()
