"""SQLite: criacao do banco, migrations, persistencia e recuperacao apos
'reinicio' (fechar a conexao e reabrir o mesmo arquivo)."""
import tempfile
import unittest
from pathlib import Path

from sdc.config import Config
from sdc.db.connection import Database
from sdc.db.migrations import current_version
from sdc.mcp.adapter import Adapter


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "sdc_test.db"
        self._open: list[Adapter] = []

    def tearDown(self):
        for a in self._open:
            a.close()
        for p in self.path.parent.glob("sdc_test.db*"):
            try:
                p.unlink()
            except (PermissionError, FileNotFoundError):
                pass  # WAL/-shm as vezes segura no Windows -- e tmp, sem impacto

    def _adapter(self):
        cfg = Config()
        cfg.db_path = self.path
        cfg.ensure_storage_dir()
        a = Adapter(cfg)
        self._open.append(a)
        return a

    def test_db_file_created(self):
        self._adapter()
        self.assertTrue(self.path.exists())

    def test_data_survives_restart(self):
        a = self._adapter()
        a.store_memory("project.name", "SecureData Central", importance="high")
        a.update_world_state("project", "sdc", "status", "development")
        a.record_event("deploy", payload={"v": "1.0"})
        a.db.close()
        del a

        b = self._adapter()  # "reinicio": conexao nova, mesmo arquivo
        self.assertEqual(b.get_memory(key="project.name")["memory"]["content"], "SecureData Central")
        self.assertEqual(b.get_world_state("project", "sdc", "status")["current"]["value"], "development")
        self.assertEqual(b.recent_changes(event_type="deploy")["count"], 1)

    def test_migrations_not_rerun_on_existing_db(self):
        a = self._adapter()
        v = current_version(a.db.conn)
        a.db.close()
        b = self._adapter()
        self.assertEqual(current_version(b.db.conn), v)
        self.assertEqual(b.db.applied_migrations, [])  # nada aplicado na 2a abertura

    def test_wal_mode_on_file_db(self):
        a = self._adapter()
        mode = a.db.query_one("PRAGMA journal_mode")[0]
        self.assertEqual(mode.lower(), "wal")

    def test_version_history_survives_restart(self):
        a = self._adapter()
        a.store_memory("k", "v1")
        a.update_memory(a.get_memory(key="k")["memory"]["id"], content="v2")
        a.db.close()
        b = self._adapter()
        hist = b.memory_history("k")
        self.assertEqual([m["version"] for m in hist["versions"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
