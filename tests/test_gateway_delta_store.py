"""Focused tests: PIE gateway passes --delta-store to the Blender bridge."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from pie.gateway import domain
from pie.storage.locations import workspace_file


def _upstream() -> list[str]:
    return [sys.executable, "-c", "print('noop')"]


def test_blender_route_includes_delta_store(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    command, tools, profile = domain.domain_route(
        "blender", _upstream(), python="python", max_chars=2400,
        delta_store=domain.workspace_delta_root(workspace),
    )
    assert profile == "generic"
    assert tools == ()
    assert command[:3] == ["python", "-m", "pie.integrations.blender_mcp_bridge"]
    i = command.index("--delta-store")
    expected = workspace.resolve()
    assert Path(command[i + 1]) == expected
    # single argv token, absolute, outside the checkout source tree
    assert " " not in command[i + 1]
    assert Path(command[i + 1]).is_absolute()


def test_blender_route_without_delta_store_keeps_legacy_shape() -> None:
    command, _tools, _profile = domain.domain_route(
        "blender", _upstream(), python="python", max_chars=2400)
    assert "--delta-store" not in command


def test_web_route_rejects_delta_store(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        domain.domain_route("web", _upstream(), python="python", max_chars=2400,
                            delta_store=tmp_path)


def test_workspace_delta_root_is_the_workspace_itself(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    a = domain.workspace_delta_root(workspace)
    b = domain.workspace_delta_root(workspace)
    assert a == b == workspace.resolve()
    # Deprecated helper kept for compatibility; documented as legacy.
    assert domain.delta_home(tmp_path / "s").name == domain.DELTA_STORE_DIRNAME


def test_domain_route_rejects_non_path_delta_store() -> None:
    with pytest.raises(ValueError):
        domain.domain_route("blender", _upstream(), python="python",
                            max_chars=2400, delta_store="../../etc/passwd")  # type: ignore[arg-type]


def test_domain_route_rejects_relative_delta_store(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        domain.domain_route("blender", _upstream(), python="python",
                            max_chars=2400, delta_store=Path("relative/dir"))


def test_register_plan_includes_delta_store(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    plan = domain.register_plan("blender", "pie-blender", _upstream(),
                                python="python",
                                delta_store=domain.workspace_delta_root(workspace))
    assert plan[0] == "codex"
    ds = plan.index("--delta-store")
    assert Path(plan[ds + 1]) == workspace.resolve()
    assert plan[ds + 2] == "--"
    # upstream command must come after -- only, never exposed elsewhere
    assert plan.count(sys.executable) == 1


def test_register_plan_backward_compatible() -> None:
    plan = domain.register_plan("blender", "pie-blender", _upstream(), python="python")
    assert "--delta-store" not in plan
    assert plan[-len(_upstream()):] == _upstream()


def test_main_serve_builds_bridge_command_with_delta_store(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ran: dict = {}
    workspace = tmp_path / "ws"
    workspace.mkdir()

    class FakeGateway:
        def __init__(self, workspace, command, max_chars=2400, compress_tools=(),
                     profile="generic", exposed_tools=()):
            ran["command"] = command

        def run(self) -> int:
            return 0

    # main() mutates os.environ (ENV_HOME and PIE_APP via setdefault); restore
    # both in finally so this test cannot leak state into later tests.
    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    original_app = os.environ.get("PIE_APP", sentinel)
    monkeypatch.setattr(domain, "MCPStdioGateway", FakeGateway)
    try:
        rc = domain.main(["serve", "--domain", "blender", "--max-chars", "2400",
                          "--workspace", str(workspace), "--", *_upstream()])
        assert rc == 0
        command = ran["command"]
        i = command.index("--delta-store")
        # Default delta store is the effective workspace root, not the
        # storage root (SceneDeltaCache contract).
        assert Path(command[i + 1]) == workspace.resolve()
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original
        if original_app is sentinel:
            os.environ.pop("PIE_APP", None)
        else:
            os.environ["PIE_APP"] = original_app


def test_main_serve_explicit_delta_store_override(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ran: dict = {}

    class FakeGateway:
        def __init__(self, workspace, command, max_chars=2400, compress_tools=(),
                     profile="generic", exposed_tools=()):
            ran["command"] = command
            root_index = command.index("--delta-store") + 1
            ran["root"] = Path(command[root_index])
            ran["db_at_start"] = workspace_file(ran["root"]).is_file()

        def run(self) -> int:
            return 0

    # main() mutates os.environ (ENV_HOME and PIE_APP via setdefault); restore
    # both in finally so this test cannot leak state into later tests.
    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    original_app = os.environ.get("PIE_APP", sentinel)
    monkeypatch.setattr(domain, "MCPStdioGateway", FakeGateway)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    custom = tmp_path / "custom-delta"
    custom.mkdir()
    try:
        rc = domain.main(["serve", "--domain", "blender", "--max-chars", "2400",
                          "--workspace", str(workspace),
                          "--delta-store", str(custom), "--", *_upstream()])
        assert rc == 0
        assert ran["root"] == custom.resolve()
        # The DB must be initialized at the override root, not --workspace.
        assert ran["db_at_start"] is True
        assert workspace_file(ran["root"]).is_file()
        assert not workspace_file(workspace).is_file()
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original
        if original_app is sentinel:
            os.environ.pop("PIE_APP", None)
        else:
            os.environ["PIE_APP"] = original_app


def test_main_serve_explicit_delta_store_override_persists(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit --delta-store override root persists across a bridge-style
    SceneDeltaCache restart (persistence_diagnostic is None)."""
    from pie.integrations.blender_delta import SceneDeltaCache

    ran: dict = {}

    class FakeGateway:
        def __init__(self, workspace, command, max_chars=2400, compress_tools=(),
                     profile="generic", exposed_tools=()):
            ran["command"] = command

        def run(self) -> int:
            return 0

    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    original_app = os.environ.get("PIE_APP", sentinel)
    monkeypatch.setattr(domain, "MCPStdioGateway", FakeGateway)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    custom = tmp_path / "custom-delta"
    custom.mkdir()
    try:
        assert domain.main(["serve", "--domain", "blender", "--max-chars", "2400",
                            "--workspace", str(workspace),
                            "--delta-store", str(custom), "--", *_upstream()]) == 0
        i = ran["command"].index("--delta-store")
        root = Path(ran["command"][i + 1])
        assert root == custom.resolve()
        snapshot = _make_snapshot()
        first = SceneDeltaCache(root=root)
        assert first.observe(snapshot)["state"] == "INITIAL"
        assert first.persistence_diagnostic is None
        second = SceneDeltaCache(root=root)
        assert second.observe(snapshot)["state"] == "UNCHANGED"
        assert second.persistence_diagnostic is None
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original
        if original_app is sentinel:
            os.environ.pop("PIE_APP", None)
        else:
            os.environ["PIE_APP"] = original_app


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_main_serve_rejects_unusable_delta_store_override(
        kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    """A nonexistent or non-directory override must fail before MCP starts."""
    started: list = []

    class FakeGateway:
        def __init__(self, *a, **kw):
            started.append(True)

        def run(self) -> int:
            raise AssertionError("gateway must not start")

    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    original_app = os.environ.get("PIE_APP", sentinel)
    monkeypatch.setattr(domain, "MCPStdioGateway", FakeGateway)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = tmp_path / "override"
    if kind == "file":
        target.write_text("not a directory", encoding="utf-8")
    try:
        rc = domain.main(["serve", "--domain", "blender", "--max-chars", "2400",
                          "--workspace", str(workspace),
                          "--delta-store", str(target), "--", *_upstream()])
        assert rc == 2
        assert started == []
        err = capsys.readouterr().err
        assert "PIE domain gateway unavailable: ValueError" in err
        # No DB was initialized anywhere as a fallback.
        assert not workspace_file(workspace).is_file()
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original
        if original_app is sentinel:
            os.environ.pop("PIE_APP", None)
        else:
            os.environ["PIE_APP"] = original_app


def test_main_register_does_not_initialize_database(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """register/dry-run must not create any DB (no workspace or override)."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    override = tmp_path / "override"
    override.mkdir()
    recorded: dict = {}

    def fake_register(domain_name, name, upstream, *, python, max_chars=2400,
                      apply=False, delta_store=None):
        recorded["delta_store"] = delta_store
        return {"state": "DRY_RUN"}

    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    original_app = os.environ.get("PIE_APP", sentinel)
    monkeypatch.setattr(domain, "register_codex", fake_register)
    try:
        rc = domain.main(["register", "--domain", "blender", "--name", "pie-blender",
                          "--max-chars", "2400", "--workspace", str(workspace),
                          "--delta-store", str(override), "--", *_upstream()])
        assert rc == 0
        assert recorded["delta_store"] == override.resolve()
        assert not workspace_file(workspace).is_file()
        assert not workspace_file(override).is_file()
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original
        if original_app is sentinel:
            os.environ.pop("PIE_APP", None)
        else:
            os.environ["PIE_APP"] = original_app


def test_bridge_accepts_delta_store_flag_smoke(tmp_path: Path) -> None:
    """The bridge CLI itself parses --delta-store (help smoke, no server run)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pie.integrations.blender_mcp_bridge", "--help"],
        capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0
    assert "--delta-store" in proc.stdout


def test_main_serve_delta_store_persists_across_bridge_restart(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: the --delta-store value main() passes to the bridge is a
    workspace root whose .pie/index.sqlite3 lets SceneDeltaCache persist and
    reload fingerprints (persistence_diagnostic is None), proving the gateway
    honours the SceneDeltaCache(root=workspace_root) contract."""
    from pie.integrations.blender_delta import SceneDeltaCache
    from pie.storage.database import connect

    ran: dict = {}
    workspace = tmp_path / "ws"
    workspace.mkdir()

    class FakeGateway:
        def __init__(self, workspace, command, max_chars=2400, compress_tools=(),
                     profile="generic", exposed_tools=()):
            ran["command"] = command

        def run(self) -> int:
            return 0

    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    original_app = os.environ.get("PIE_APP", sentinel)
    monkeypatch.setattr(domain, "MCPStdioGateway", FakeGateway)
    try:
        assert domain.main(["serve", "--domain", "blender", "--max-chars", "2400",
                            "--workspace", str(workspace), "--", *_upstream()]) == 0
        command = ran["command"]
        i = command.index("--delta-store")
        root = Path(command[i + 1])
        assert root == workspace.resolve()
        # main() has already initialized the workspace DB wherever
        # workspace_storage resolves it; no manual `pie init` emulation.
        snapshot = {
            "schema": "pie-blender-scene-snapshot-v1",
            "scene": "Scene",
            "scope": "selected",
            "complete": True,
            "omissions": {"objects": 0, "materials": 0},
            "objects": [{"name": "Cube", "type": "MESH",
                         "location": [0.0, 0.0, 0.0]}],
            "materials": [{"name": "Material", "nodes": [], "links": []}],
        }
        first = SceneDeltaCache(root=root)
        assert first.observe(snapshot)["state"] == "INITIAL"
        assert first.persistence_diagnostic is None
        second = SceneDeltaCache(root=root)
        assert second.observe(snapshot)["state"] == "UNCHANGED"
        assert second.persistence_diagnostic is None
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original
        if original_app is sentinel:
            os.environ.pop("PIE_APP", None)
        else:
            os.environ["PIE_APP"] = original_app


def _make_snapshot():
    from tests.test_blender_delta_persistence import make_snapshot as factory
    return factory()


def test_main_serve_initializes_workspace_db_under_global_storage(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve must init the PIE DB before the gateway starts, even with a
    global storage root, so the bridge's SceneDeltaCache(root=workspace)
    persists instead of reporting a persistence diagnostic."""
    from pie.integrations.blender_delta import SceneDeltaCache
    from pie.storage.locations import workspace_file

    ran: dict = {}

    class FakeGateway:
        def __init__(self, workspace, command, max_chars=2400, compress_tools=(),
                     profile="generic", exposed_tools=()):
            ran["command"] = command
            # Gateway start must happen only after the DB exists.
            root_index = command.index("--delta-store") + 1
            ran["root"] = Path(command[root_index])
            ran["db_at_start"] = workspace_file(ran["root"]).is_file()

        def run(self) -> int:
            return 0

    workspace = tmp_path / "ws"
    workspace.mkdir()
    global_root = tmp_path / "global"

    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    original_app = os.environ.get("PIE_APP", sentinel)
    monkeypatch.setattr(domain, "MCPStdioGateway", FakeGateway)
    try:
        assert domain.main(["serve", "--domain", "blender", "--max-chars", "2400",
                            "--workspace", str(workspace),
                            "--store", str(global_root), "--", *_upstream()]) == 0
        root = ran["root"]
        assert root == workspace.resolve()
        assert ran["db_at_start"] is True
        db_path = workspace_file(root)
        # The DB lives in the global store, not in ws/.pie.
        assert db_path.is_file()
        assert db_path.parent.parent == global_root.resolve() / "projects"
        assert not (workspace / ".pie").exists()
        snapshot = {
            "schema": "pie-blender-scene-snapshot-v1",
            "scene": "Scene",
            "scope": "selected",
            "complete": True,
            "omissions": {"objects": 0, "materials": 0},
            "objects": [{"name": "Cube", "type": "MESH",
                         "location": [0.0, 0.0, 0.0]}],
            "materials": [{"name": "Material", "nodes": [], "links": []}],
        }
        first = SceneDeltaCache(root=root)
        assert first.observe(snapshot)["state"] == "INITIAL"
        assert first.persistence_diagnostic is None
        second = SceneDeltaCache(root=root)
        assert second.observe(snapshot)["state"] == "UNCHANGED"
        assert second.persistence_diagnostic is None
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original
        if original_app is sentinel:
            os.environ.pop("PIE_APP", None)
        else:
            os.environ["PIE_APP"] = original_app


def test_ensure_workspace_database_is_idempotent_and_never_overwrites(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    global_root = tmp_path / "global"
    sentinel = object()
    original = os.environ.get(domain.ENV_HOME, sentinel)
    try:
        os.environ[domain.ENV_HOME] = str(global_root)
        from pie.storage.database import connect
        from pie.storage.locations import workspace_file

        first = domain.ensure_workspace_database(workspace)
        assert first.is_file()
        with connect(first) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS marker(value TEXT)")
            conn.execute("INSERT INTO marker(value) VALUES ('kept')")
            conn.commit()
        second = domain.ensure_workspace_database(workspace)
        assert second == first
        with connect(second) as conn:
            rows = conn.execute("SELECT value FROM marker").fetchall()
        assert [row[0] for row in rows] == ["kept"]
    finally:
        if original is sentinel:
            os.environ.pop(domain.ENV_HOME, None)
        else:
            os.environ[domain.ENV_HOME] = original