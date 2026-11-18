from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_mcp_suite.py"
SPEC = importlib.util.spec_from_file_location("install_mcp_suite", SCRIPT)
assert SPEC and SPEC.loader
MCP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MCP)


class McpSuiteTests(unittest.TestCase):
    def test_safe_defaults(self) -> None:
        state = MCP.activation({})
        self.assertTrue(state["dfyqq-korea-public"][0])
        self.assertFalse(state["dfyqq-naver-search"][0])
        self.assertFalse(state["dfyqq-china-shopping"][0])
        self.assertFalse(state["dfyqq-global-shopping"][0])
        self.assertEqual(
            MCP.desired_servers({})["dfyqq-global-shopping"]["command"],
            "buywhere-mcp",
        )

    def test_credentials_enable_only_their_domain(self) -> None:
        naver = MCP.activation({"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "secret"})
        self.assertTrue(naver["dfyqq-naver-search"][0])
        self.assertFalse(naver["dfyqq-china-shopping"][0])

        pdd = MCP.activation(
            {"PDD_CLIENT_ID": "id", "PDD_CLIENT_SECRET": "secret", "PDD_PID": "pid"}
        )
        self.assertTrue(pdd["dfyqq-china-shopping"][0])
        self.assertFalse(pdd["dfyqq-naver-search"][0])

    def test_mock_is_not_exposed_by_default(self) -> None:
        forced = MCP.activation(
            {
                "PDD_CLIENT_ID": "id",
                "PDD_CLIENT_SECRET": "secret",
                "PDD_PID": "pid",
                "SHOPPING_MCP_MOCK": "1",
            }
        )
        self.assertFalse(forced["dfyqq-china-shopping"][0])
        explicit = MCP.activation({"DFYQQ_MCP_ALLOW_MOCK": "1"})
        self.assertTrue(explicit["dfyqq-china-shopping"][0])

    def test_install_preserves_unmanaged_and_never_serializes_secrets(self) -> None:
        env = {
            "NAVER_CLIENT_ID": "visible-id-must-not-be-written",
            "NAVER_CLIENT_SECRET": "super-secret-must-not-be-written",
        }
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            config = data / "mcp_server.json"
            config.write_text(
                json.dumps({"mcpServers": {"custom": {"url": "https://example.test/mcp"}}}),
                encoding="utf-8",
            )
            backup = MCP.install(config, env, data / "backups")
            self.assertIsNotNone(backup)
            result = json.loads(config.read_text(encoding="utf-8"))
            self.assertIn("custom", result["mcpServers"])
            self.assertTrue(result["mcpServers"]["dfyqq-naver-search"]["active"])
            raw = config.read_text(encoding="utf-8")
            self.assertNotIn(env["NAVER_CLIENT_ID"], raw)
            self.assertNotIn(env["NAVER_CLIENT_SECRET"], raw)
            self.assertTrue(MCP.is_current(config, env))


if __name__ == "__main__":
    unittest.main()
