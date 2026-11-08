"""Testes de regressão para o benchmark PIE vs SEM PIE.

Cobre a causa raiz diagnosticada: o OpenCode 2.2.5 apenas registra o MCP
pie no /api/mcp após alguns segundos de inicialização do servidor stdio.
O benchmark não pode prosseguir apenas com a porta TCP aberta; deve
aguardar a conexão efetiva do MCP antes de executar as perguntas.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from pie.orchestrator.opencode_v2 import OpenCodeV2Adapter
from benchmark_opencode_pair import _root_and_mcp


class FakeAdapter(OpenCodeV2Adapter):
    """Adapter que simula respostas da API /api/mcp sem rede real."""

    def __init__(self, mcp_response: dict):
        super().__init__("http://127.0.0.1:9999", "test-password")
        self.mcp_response = mcp_response

    def _request(self, method: str, path: str, body=None):
        if path == "/mcp":
            return self.mcp_response
        raise AssertionError(f"Unexpected request {method} {path}")


class RootAndMcpTests(unittest.TestCase):
    """_root_and_mcp deve aceitar/rejeitar conforme o estado real do MCP."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def _mcp_connected(self):
        return {
            "location": {"directory": str(self.root)},
            "data": [{"name": "pie", "status": {"status": "connected"}}],
        }

    def _mcp_empty(self):
        return {"location": {"directory": str(self.root)}, "data": []}

    def _mcp_doctor_mesh(self):
        return {
            "location": {"directory": str(self.root)},
            "data": [{"name": "pie-doctor-mesh", "status": {"status": "connected"}}],
        }

    def _mcp_wrong_location(self):
        return {
            "location": {"directory": "C:/DoctorMesh"},
            "data": [{"name": "pie", "status": {"status": "connected"}}],
        }

    def test_with_pie_connected_is_accepted(self):
        adapter = FakeAdapter(self._mcp_connected())
        result = _root_and_mcp(adapter, self.root, True)
        self.assertTrue(result["mcp_pie"])
        self.assertTrue(result["root_verified"])

    def test_with_pie_not_connected_is_rejected(self):
        adapter = FakeAdapter(self._mcp_empty())
        with self.assertRaisesRegex(RuntimeError, "WITH_PIE server lacks connected pie MCP"):
            _root_and_mcp(adapter, self.root, True)

    def test_with_pie_doctor_mesh_only_is_rejected(self):
        adapter = FakeAdapter(self._mcp_doctor_mesh())
        with self.assertRaisesRegex(RuntimeError, "WITH_PIE server lacks connected pie MCP"):
            _root_and_mcp(adapter, self.root, True)

    def test_with_pie_wrong_location_is_rejected(self):
        adapter = FakeAdapter(self._mcp_wrong_location())
        with self.assertRaisesRegex(RuntimeError, "Server workspace is not the authorized root"):
            _root_and_mcp(adapter, self.root, True)

    def test_without_pie_no_mcp_is_accepted(self):
        adapter = FakeAdapter(self._mcp_empty())
        result = _root_and_mcp(adapter, self.root, False)
        self.assertFalse(result["mcp_pie"])
        self.assertTrue(result["root_verified"])

    def test_without_pie_still_exposes_pie_is_rejected(self):
        adapter = FakeAdapter(self._mcp_connected())
        with self.assertRaisesRegex(RuntimeError, "WITHOUT_PIE server still exposes pie MCP"):
            _root_and_mcp(adapter, self.root, False)


if __name__ == "__main__":
    unittest.main()
