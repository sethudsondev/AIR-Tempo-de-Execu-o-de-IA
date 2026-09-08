"""Testes do servidor MCP em si -- inicializacao, tools declaradas,
schemas validos, chamada valida/invalida."""
import asyncio
import os
import unittest


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(w.capitalize() for w in rest)


class TestMcpServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SDC_DB_PATH"] = ":memory:"
        os.environ["SDC_LOG_LEVEL"] = "WARNING"
        # importado depois de setar o ambiente
        import importlib

        import sdc.config
        import sdc.mcp.adapter
        import sdc.mcp.server as server_mod

        importlib.reload(sdc.config)
        importlib.reload(sdc.mcp.adapter)
        importlib.reload(server_mod)
        cls.server_mod = server_mod
        cls.server = server_mod.server

    EXPECTED = {
        "sdc_store_memory", "sdc_get_memory", "sdc_search_memory", "sdc_update_memory",
        "sdc_delete_memory", "sdc_memory_history", "sdc_update_world_state",
        "sdc_get_world_state", "sdc_world_history", "sdc_record_event",
        "sdc_recent_changes", "sdc_search_context", "sdc_get_context", "sdc_status",
    }

    def test_all_tools_registered(self):
        tools = _run(self.server.list_tools())
        names = {t.name for t in tools}
        self.assertEqual(names, self.EXPECTED)

    @staticmethod
    def _schema(tool):
        return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)

    @staticmethod
    def _ann(annotations, name):
        return getattr(annotations, name, None) or getattr(annotations, _camel(name), None)

    def test_tools_have_schema_and_description(self):
        for t in _run(self.server.list_tools()):
            self.assertTrue(t.description, f"{t.name} sem descricao")
            schema = self._schema(t)
            self.assertIsInstance(schema, dict)
            self.assertEqual(schema.get("type"), "object")

    def test_destructive_annotation(self):
        by_name = {t.name: t for t in _run(self.server.list_tools())}
        self.assertTrue(self._ann(by_name["sdc_delete_memory"].annotations, "destructive_hint"))
        self.assertTrue(self._ann(by_name["sdc_search_context"].annotations, "read_only_hint"))

    def test_valid_call(self):
        res = _run(self.server.call_tool("sdc_store_memory", {"key": "project.name", "content": "SecureData Central"}))
        # call_tool devolve (content, structured) ou content -- normaliza
        payload = res[1] if isinstance(res, tuple) else res
        text = str(payload)
        self.assertIn("ok", text)
        self.assertIn("SecureData Central", text)

    def test_invalid_call_missing_required(self):
        with self.assertRaises(Exception):
            _run(self.server.call_tool("sdc_store_memory", {"content": "sem key"}))

    def test_invalid_call_unknown_tool(self):
        with self.assertRaises(Exception):
            _run(self.server.call_tool("sdc_nao_existe", {}))

    def test_resources_and_prompt(self):
        resources = _run(self.server.list_resources())
        uris = {str(r.uri) for r in resources}
        self.assertIn("sdc://memory/active", uris)
        self.assertIn("sdc://world/state", uris)
        prompts = _run(self.server.list_prompts())
        self.assertIn("reconstruct_context", {p.name for p in prompts})


if __name__ == "__main__":
    unittest.main()
