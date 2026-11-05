from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from verify_opencode_runtime import check_contract


class OpenCodeRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = {
            "mcp": {"servers": {"pie": {
                "type": "local", "codemode": False,
                "command": ["C:/Python/python.exe", "-m",
                            "pie.interfaces.mcp_server", "--root", str(self.root)]
            }}},
            "permissions": [
                {"action": x, "resource": "*", "effect": "deny"}
                for x in ("shell", "edit", "subagent", "webfetch",
                          "websearch", "external_directory", "execute")
            ]
        }
        self.info = {"name": "opencode"}
        self.mcp = {"location": {"directory": str(self.root)},
                    "data": [{"name": "pie", "status": {"status": "connected"}}]}
        self.active = {"data": {}}

    def check(self):
        return check_contract(self.config, self.info, self.mcp,
                              self.active, self.root)

    def test_v2_schema_connects(self):
        self.assertEqual(self.check()["session_api"], "v2")

    def test_wrong_pie_root_fails(self):
        self.config["mcp"]["servers"]["pie"]["command"][-1] = "C:/DoctorMesh"
        with self.assertRaisesRegex(ValueError, "root mismatch"):
            self.check()

    def test_doctor_mesh_is_not_pie(self):
        self.mcp["data"] = [{"name": "pie-doctor-mesh", "status": {"status": "connected"}}]
        with self.assertRaisesRegex(ValueError, "not connected"):
            self.check()

    def test_missing_permission_fails(self):
        self.config["permissions"] = []
        with self.assertRaisesRegex(ValueError, "permissions"):
            self.check()

    def test_wrong_location_fails(self):
        self.mcp["location"]["directory"] = "C:/DoctorMesh"
        with self.assertRaisesRegex(ValueError, "another directory"):
            self.check()

    def test_v1_data_shape_rejected(self):
        self.mcp = {"pie": {"status": "connected"}}
        with self.assertRaises(ValueError):
            self.check()
