"""Modulos de runtime: permissions, event bus, verification, planner,
tool registry, model provider, filesystem, process."""
import tempfile
import unittest
from pathlib import Path

from tests.helpers import fresh_db
from sdc.context.engine import ContextEngine
from sdc.context.retrieval import Retriever
from sdc.core.types import ActionResult, Capability, TaskStatus, VerificationOutcome, new_id
from sdc.events.bus import EventBus
from sdc.events.log import EventLog
from sdc.filesystem.fs import FsError, list_dir, read_file, write_file
from sdc.memory.store import MemoryStore
from sdc.models.provider import EchoProvider
from sdc.planner.planner import Planner
from sdc.process.proc import ProcError, run_command
from sdc.security.permissions import PermissionDenied, PermissionManager
from sdc.tools.registry import ToolRegistry
from sdc.verification.engine import VerificationEngine, expect_substring
from sdc.world.state import WorldState


class TestPermissions(unittest.TestCase):
    def test_deny_by_default(self):
        pm = PermissionManager()
        self.assertFalse(pm.check("agent:main", Capability.READ))
        with self.assertRaises(PermissionDenied):
            pm.require("agent:main", Capability.READ)

    def test_grant_and_scope(self):
        pm = PermissionManager()
        pm.grant("agent:main", Capability.FILESYSTEM, "/proj/**")
        self.assertTrue(pm.check("agent:main", Capability.FILESYSTEM, "/proj/src/a.py"))
        self.assertFalse(pm.check("agent:main", Capability.FILESYSTEM, "/etc/passwd"))
        self.assertFalse(pm.check("other", Capability.FILESYSTEM, "/proj/x"))

    def test_revoke(self):
        pm = PermissionManager()
        g = pm.grant("a", Capability.WRITE)
        pm.revoke(g.id)
        self.assertFalse(pm.check("a", Capability.WRITE))


class TestEventBus(unittest.TestCase):
    def test_pub_sub_and_wildcard(self):
        bus = EventBus()
        seen = []
        bus.subscribe("task.failed", lambda t, p: seen.append(("h1", t, p["id"])))
        bus.subscribe("*", lambda t, p: seen.append(("wild", t)))
        bus.publish("task.failed", {"id": "t1"})
        self.assertIn(("h1", "task.failed", "t1"), seen)
        self.assertIn(("wild", "task.failed"), seen)

    def test_unsubscribe_unknown_topic_no_leak(self):
        bus = EventBus()
        bus.unsubscribe("never.subscribed", lambda *a: None)
        self.assertNotIn("never.subscribed", bus._subs)


class TestVerification(unittest.TestCase):
    def test_heuristic(self):
        ve = VerificationEngine()
        ok = ve.verify(ActionResult(id="a", tool_name="x", args={}, output="feito"))
        self.assertEqual(ok.outcome, VerificationOutcome.OK)
        fail = ve.verify(ActionResult(id="a", tool_name="x", args={}, output=None, error="boom"))
        self.assertEqual(fail.outcome, VerificationOutcome.FAILED)
        unk = ve.verify(ActionResult(id="a", tool_name="x", args={}, output=""))
        self.assertEqual(unk.outcome, VerificationOutcome.UNKNOWN)

    def test_specific_verifier(self):
        ve = VerificationEngine()
        ve.register("greet", expect_substring("ola"))
        r = ve.verify(ActionResult(id="a", tool_name="greet", args={}, output="ola mundo"))
        self.assertEqual(r.outcome, VerificationOutcome.OK)
        r2 = ve.verify(ActionResult(id="a", tool_name="greet", args={}, output="hi"))
        self.assertEqual(r2.outcome, VerificationOutcome.FAILED)


class TestPlanner(unittest.TestCase):
    def test_dependency_order_and_verify(self):
        planner = Planner()
        goal = planner.new_goal("reconstruir contexto")
        t1 = planner.add_task(goal, "retrieve")
        t2 = planner.add_task(goal, "assemble", depends_on=[t1.id])
        ran = []

        def action(task):
            ran.append(task.description)
            return ActionResult(id=new_id("act"), tool_name=task.description, args={}, output="ok")

        planner.run_all(goal, action)
        self.assertEqual(ran, ["retrieve", "assemble"])
        self.assertEqual([t.status for t in goal.tasks], [TaskStatus.DONE, TaskStatus.DONE])

    def test_stops_on_failure(self):
        planner = Planner()
        goal = planner.new_goal("g")
        a = planner.add_task(goal, "a")
        planner.add_task(goal, "b", depends_on=[a.id])

        def action(task):
            err = "falhou" if task.description == "a" else None
            return ActionResult(id=new_id("act"), tool_name=task.description, args={}, output=None, error=err)

        planner.run_all(goal, action)
        self.assertEqual(goal.tasks[0].status, TaskStatus.FAILED)
        self.assertEqual(goal.tasks[1].status, TaskStatus.PENDING)


class TestToolRegistry(unittest.TestCase):
    def _ctx(self):
        db = fresh_db()
        r = Retriever(MemoryStore(db), WorldState(db), EventLog(db))
        return ContextEngine(db, r)

    def test_permission_denied_becomes_action_result(self):
        pm = PermissionManager()
        reg = ToolRegistry(pm, self._ctx())
        reg.register("danger", lambda: "x", required_capability=Capability.EXECUTE)
        res = reg.call("agent:main", "danger")
        self.assertIsNone(res.output)
        self.assertIn("execute", res.error)

    def test_granted_tool_runs(self):
        pm = PermissionManager()
        pm.grant("agent:main", Capability.EXECUTE)
        reg = ToolRegistry(pm, self._ctx())
        reg.register("ok", lambda x: x * 2, required_capability=Capability.EXECUTE)
        self.assertEqual(reg.call("agent:main", "ok", x=3).output, 6)

    def test_large_output_becomes_handle(self):
        reg = ToolRegistry(PermissionManager(), self._ctx())
        reg.register("big", lambda: "z" * 5000)
        res = reg.call("agent:main", "big")
        self.assertIn("handle", res.output)
        self.assertIn("preview", res.output)

    def test_unknown_tool(self):
        reg = ToolRegistry(PermissionManager(), self._ctx())
        self.assertIn("desconhecida", reg.call("a", "nope").error)


class TestModelProvider(unittest.TestCase):
    def test_echo(self):
        c = EchoProvider().complete("contexto util\n\nPergunta: e o nome?")
        self.assertEqual(c.method, "echo")
        self.assertIn("contexto util", c.text)
        self.assertIn("Pergunta: e o nome?", c.text)


class TestFilesystem(unittest.TestCase):
    def test_roundtrip_and_root_confinement(self):
        root = Path(tempfile.mkdtemp())
        write_file(str(root / "a.txt"), "conteudo", root=root)
        self.assertEqual(read_file(str(root / "a.txt"), root=root), "conteudo")
        self.assertIn("a.txt", list_dir(str(root), root=root))
        with self.assertRaises(FsError):
            read_file("/etc/hosts", root=root)


class TestProcess(unittest.TestCase):
    def test_allowlist_blocks_unknown_binary(self):
        with self.assertRaises(ProcError):
            run_command("rm -rf /")

    def test_allowed_binary_runs(self):
        out = run_command(["echo", "ola"])
        self.assertIn("ola", out)


if __name__ == "__main__":
    unittest.main()
