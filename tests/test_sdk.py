import unittest

from sdc.core.types import Capability
from sdc.sdk import Agent, MemoryAgent


class TestSdkAgent(unittest.TestCase):
    def setUp(self):
        self.agent = Agent("agent:test", db_path=":memory:")

    def tearDown(self):
        self.agent.close()

    def test_memory_and_state_shortcuts(self):
        self.agent.remember("project.name", "SecureData Central", importance="high")
        self.assertEqual(self.agent.recall("project.name"), "SecureData Central")
        self.agent.set_state("project", "sdc", "status", "development")
        self.assertEqual(self.agent.get_state("project", "sdc", "status"), "development")

    def test_ask_uses_persistent_context(self):
        self.agent.remember("project.name", "SecureData Central", importance="critical")
        answer = self.agent.ask("qual o nome do projeto SecureData", session_id="s1")
        self.assertIn("SecureData Central", answer)  # EchoProvider ecoa o contexto recebido

    def test_tool_with_capability(self):
        self.agent.grant(Capability.EXECUTE)
        self.agent.register_tool("double", lambda n: n * 2, capability=Capability.EXECUTE)
        self.assertEqual(self.agent.call_tool("double", n=21).output, 42)

    def test_tool_without_capability_is_denied(self):
        self.agent.register_tool("secret", lambda: "x", capability=Capability.EXECUTE)
        self.assertIsNone(self.agent.call_tool("secret").output)


class TestMemoryAgentFacade(unittest.TestCase):
    def test_reexported(self):
        a = MemoryAgent.__init__  # noqa: F841  -- so garante que o import de sdc.sdk expõe MemoryAgent
        self.assertTrue(callable(MemoryAgent))


if __name__ == "__main__":
    unittest.main()
