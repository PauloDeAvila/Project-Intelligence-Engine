import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_opencode_runtime import check_contract


class OpenCodeRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = {
            "mcp": {"pie": {"type": "local", "enabled": True,
                "command": ["C:/Python312/python.exe", "-m",
                    "pie.interfaces.mcp_server", "--root", str(self.root)]}},
            "permission": {"bash": "deny", "edit": "deny",
                "webfetch": "deny", "external_directory": "deny"},
        }
        self.status = {"pie": {"status": "connected"}}
        self.tools = ["pie_project_status", "pie_query"]

    def test_22_compatible_shape(self):
        result = check_contract(self.config, self.status, {}, self.tools, self.root)
        self.assertEqual(result["pie_mcp"], "connected")

    def test_wrong_workspace_fails_closed(self):
        self.config["mcp"]["pie"]["command"][-1] = "C:/DoctorMesh"
        with self.assertRaisesRegex(ValueError, "root mismatch"):
            check_contract(self.config, self.status, {}, self.tools, self.root)

    def test_unconnected_pie_fails(self):
        with self.assertRaisesRegex(ValueError, "not connected"):
            check_contract(self.config, {"pie-doctor-mesh": {"status": "connected"}},
                           {}, self.tools, self.root)

    def test_missing_tool_fails(self):
        with self.assertRaisesRegex(ValueError, "not available"):
            check_contract(self.config, self.status, {}, ["read"], self.root)

    def test_missing_denial_fails(self):
        self.config["permission"]["bash"] = "allow"
        with self.assertRaisesRegex(ValueError, "permission"):
            check_contract(self.config, self.status, {}, self.tools, self.root)

    def test_unexpected_session_contract_fails(self):
        with self.assertRaisesRegex(ValueError, "contract mismatch"):
            check_contract(self.config, self.status, [], self.tools, self.root)


if __name__ == "__main__":
    unittest.main()
