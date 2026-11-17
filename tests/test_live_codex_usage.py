import json

import pytest

import pie.certification.live_codex as live_codex
from pie.certification.live_codex import CodexCaptureError, parse_codex_jsonl


def _trace(usage_extra):
    usage = {"input_tokens": 100, "cached_input_tokens": 10,
             "output_tokens": 50}
    usage.update(usage_extra)
    return '{"type":"turn.completed","usage":' + \
        __import__("json").dumps(usage) + '}'


def test_missing_reasoning_output_tokens_is_none():
    out = parse_codex_jsonl(_trace({}))
    assert out["usage"]["reasoning_output_tokens"] is None
    assert out["usage"]["input_tokens"] == 100
    assert out["usage"]["cached_input_tokens"] == 10
    assert out["usage"]["output_tokens"] == 50


def test_valid_usage_parses():
    out = parse_codex_jsonl(_trace({"reasoning_output_tokens": 20}))
    assert out["usage"]["reasoning_output_tokens"] == 20
    assert out["provider_reported"] is True


def test_reasoning_exceeding_output_fails():
    with pytest.raises(ValueError):
        parse_codex_jsonl(_trace({"reasoning_output_tokens": 60}))


def test_blender_upstream_probe_fails_closed(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(live_codex.socket, "create_connection", unavailable)
    result = live_codex._probe_blender_upstream({"env": {}})
    assert result == {"state": "FAIL", "host": "127.0.0.1", "port": 9876,
                      "reason": "UPSTREAM_UNAVAILABLE"}


def test_blender_upstream_probe_uses_configured_endpoint(monkeypatch):
    seen = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def available(address, timeout):
        seen["address"] = address
        seen["timeout"] = timeout
        return Connection()

    monkeypatch.setattr(live_codex.socket, "create_connection", available)
    result = live_codex._probe_blender_upstream({
        "env": {"BLENDER_MCP_HOST": "127.0.0.2", "BLENDER_MCP_PORT": "9987"}
    })
    assert result == {"state": "PASS", "host": "127.0.0.2", "port": 9987}
    assert seen == {"address": ("127.0.0.2", 9987), "timeout": 0.75}


def test_preflight_blocks_blender_before_provider_when_upstream_is_down(
        monkeypatch, tmp_path):
    import sys

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    command = json.dumps(sys.executable)
    (codex_home / "config.toml").write_text(
        f'model = "gpt-test"\n\n[mcp_servers.blender]\ncommand = {command}\n',
        encoding="utf-8")
    scenario = {
        "schema": "pie-scenario-v1",
        "scenario_id": "blender-preflight-0001",
        "prompt": "read the scene",
        "expected_exact": "ok",
        "model": "gpt-test",
        "required_mcp_server": "blender",
    }
    monkeypatch.setattr(live_codex, "_git_clean_commit", lambda root: "a" * 40)
    monkeypatch.setattr(live_codex, "_auth_state", lambda *args: "AUTH_PRESENT_ENV")
    monkeypatch.setattr(
        live_codex, "_probe_blender_upstream",
        lambda selected: {"state": "FAIL", "reason": "UPSTREAM_UNAVAILABLE"},
    )
    result = live_codex.preflight_codex(
        scenario,
        condition="baseline",
        workspace=workspace,
        codex_home=codex_home,
    )
    assert result["state"] == "BLOCKED"
    assert "PRECHECK_BLENDER_UPSTREAM_UNAVAILABLE" in result["errors"]


@pytest.mark.parametrize("bad", ["20", 20.5, True])
def test_invalid_reasoning_output_tokens_type_fails(bad):
    with pytest.raises(ValueError):
        parse_codex_jsonl(_trace({"reasoning_output_tokens": bad}))


@pytest.mark.parametrize("missing", ["input_tokens", "cached_input_tokens",
                                     "output_tokens"])
def test_missing_required_tokens_fails(missing):
    trace = parse_codex_jsonl(_trace({"reasoning_output_tokens": 20}))
    usage = dict(trace["usage"])
    usage.pop(missing)
    line = '{"type":"turn.completed","usage":' + \
        __import__("json").dumps(usage) + '}'
    with pytest.raises(ValueError):
        parse_codex_jsonl(line)


SCENARIO = {"schema": "pie-scenario-v1", "scenario_id": "test-scenario-0001",
            "prompt": "do the thing", "expected_exact": "the result",
            "model": "gpt-test", "description": "unit fixture"}


def _timeout_stdout():
    return "\n".join([
        json.dumps({"type": "item.started", "item": {"type": "command_execution"}}),
        json.dumps({"type": "item.completed",
                    "item": {"type": "mcp_tool_call", "server": "pie-server",
                             "tool": "do_thing", "status": "completed"}}),
        "not json at all",
    ])


def _stub_environment(monkeypatch, tmp_path, *, timeout):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    monkeypatch.setattr(live_codex, "validate_scenario", lambda s: s)
    monkeypatch.setattr(live_codex, "_git_clean_commit", lambda w: "0" * 40)
    monkeypatch.setattr(live_codex, "_materialize_runtime_profile",
                        lambda *a, **k: (None, None))
    monkeypatch.setattr(live_codex, "_codex_environment",
                        lambda *a, **k: (dict(), "cfgsha123"))
    monkeypatch.setattr(live_codex, "preflight_codex",
                        lambda *a, **k: {"state": "READY_FOR_BENCHMARK",
                                         "errors": []})
    monkeypatch.setattr(live_codex.shutil, "which", lambda b: "codex-fake")
    monkeypatch.setattr(live_codex.subprocess, "run", _fake_run(timeout))


def _fake_run(timeout):
    def fake_run(args, **kwargs):
        if "--version" in args:
            return type("R", (), {"returncode": 0,
                                  "stdout": "codex-cli 1.2.3\n",
                                  "stderr": ""})()
        if timeout:
            raise live_codex.subprocess.TimeoutExpired(
                "codex", 240, output=_timeout_stdout(),
                stderr="boom\n")
        raise AssertionError("unexpected subprocess call")
    return fake_run


def test_timeout_preserves_evidence(monkeypatch, tmp_path):
    _stub_environment(monkeypatch, tmp_path, timeout=True)
    with pytest.raises(CodexCaptureError) as excinfo:
        live_codex.capture_codex(SCENARIO, condition="baseline",
                                 repetition=1, workspace=tmp_path / "workspace",
                                 codex_home=tmp_path / "codex-home")
    err = excinfo.value
    evidence = err.evidence
    assert evidence["timed_out"] is True
    assert evidence["run_id"] == live_codex._capture_run_id(
        SCENARIO, "baseline", 1)
    assert evidence["pair_id"] == live_codex._capture_pair_id(SCENARIO)
    assert evidence["event_count"] >= 1
    assert evidence["mcp_event_count"] == 1
    import pathlib
    root = pathlib.Path(evidence["forensic_path"])
    for name in ("codex-events.jsonl", "mcp-tool-events.jsonl",
                 "run-result.json", "manifest.json"):
        assert (root / name).is_file()
    result = json.loads((root / "run-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "timeout"
    assert result["timed_out"] is True


def test_error_without_evidence_has_empty_dict():
    err = CodexCaptureError("boom")
    assert err.evidence == {}
    assert str(err) == "boom"


def test_jsonl_parse_failure_evidence(monkeypatch, tmp_path):
    _stub_environment(monkeypatch, tmp_path, timeout=False)

    def fake_run(args, **kwargs):
        if "--version" in args:
            return type("R", (), {"returncode": 0,
                                  "stdout": "codex-cli 1.2.3\n",
                                  "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "not json\n",
                              "stderr": ""})()
    monkeypatch.setattr(live_codex.subprocess, "run", fake_run)
    with pytest.raises(CodexCaptureError) as excinfo:
        live_codex.capture_codex(SCENARIO, condition="baseline",
                                 repetition=1, workspace=tmp_path / "workspace",
                                 codex_home=tmp_path / "codex-home")
    evidence = excinfo.value.evidence
    assert evidence["event_count"] >= 1
    assert evidence["mcp_event_count"] == 0
    assert evidence["certification_status"] == "PROVIDER_USAGE_FAILED"
    assert evidence["forensic_path"]


def _controller_env(monkeypatch, tmp_path):
    import pie.certification.controller as controller
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(controller, "validate_scenario", lambda s: s)
    monkeypatch.setattr(controller, "_application", lambda s: "blender")
    monkeypatch.setattr(controller, "_fixture_oracle", lambda s, w: {"passed": True})
    return controller, workspace


_LEAK_STRINGS = ("do the thing", "the result", "secret-key", "api-token")


def _assert_terminal_record(path, *, status, run_id, pair_id):
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["schema"] == "pie-phase3-terminal-record-v1"
    assert record["status"] == status
    assert record["run_id"] == run_id
    assert record["pair_id"] == pair_id
    assert record["tokens"] is None
    assert record["latency_ms"] is None
    assert record["usage"] is None
    assert record["timestamp"]
    assert record["reason"] in {
        "preflight_failed", "capture_failed", "timeout",
        "identity_mismatch", "oracle_failed", "route_evidence_failed"}
    return record


def test_run_single_preflight_bypass_writes_terminal_record(monkeypatch, tmp_path):
    controller, workspace = _controller_env(monkeypatch, tmp_path)
    monkeypatch.setattr(controller, "preflight_codex",
                        lambda *a, **k: {"state": "PREFLIGHT_FAILED",
                                         "errors": ["codex missing"]})
    output = tmp_path / "out" / "result.json"
    result = controller.run_single(
        scenario=SCENARIO, application="blender", condition="baseline",
        workspace=workspace, baseline_home=tmp_path / "h1",
        optimized_home=tmp_path / "h2", baseline_profile="p",
        optimized_profile="p", output=output)
    assert result["certification_status"] == "BYPASS"
    path = tmp_path / "out" / (
        "result-terminal-" + result["run_id"] + "-" + result["pair_id"] + ".json")
    _assert_terminal_record(path, status="BYPASS",
                            run_id=result["run_id"], pair_id=result["pair_id"])


def test_run_single_capture_timeout_writes_terminal_record(monkeypatch, tmp_path):
    controller, workspace = _controller_env(monkeypatch, tmp_path)
    monkeypatch.setattr(controller, "preflight_codex",
                        lambda *a, **k: {"state": "READY_FOR_BENCHMARK",
                                         "errors": []})
    monkeypatch.setattr(controller, "capture_codex",
                        _raise_capture(CodexCaptureError(
                            "capture boom",
                            evidence={"certification_status": "TIMEOUT"})))
    output = tmp_path / "out" / "result.json"
    result = controller.run_single(
        scenario=SCENARIO, application="blender", condition="optimized",
        workspace=workspace, baseline_home=tmp_path / "h1",
        optimized_home=tmp_path / "h2", baseline_profile="p",
        optimized_profile="p", output=output,
        run_id_override="run-timeout-1", pair_id_override="pair-timeout-1")
    assert result["certification_status"] == "TIMEOUT"
    path = tmp_path / "out" / "result-terminal-run-timeout-1-pair-timeout-1.json"
    _assert_terminal_record(path, status="TIMEOUT",
                            run_id="run-timeout-1", pair_id="pair-timeout-1")


def test_run_single_two_attempts_preserve_distinct_records(monkeypatch, tmp_path):
    controller, workspace = _controller_env(monkeypatch, tmp_path)
    monkeypatch.setattr(controller, "preflight_codex",
                        lambda *a, **k: {"state": "READY_FOR_BENCHMARK",
                                         "errors": []})
    monkeypatch.setattr(controller, "capture_codex",
                        _raise_capture(CodexCaptureError(
                            "capture boom",
                            evidence={"certification_status": "TIMEOUT"})))
    output = tmp_path / "out" / "result.json"
    for run_id, pair_id in (("run-a", "pair-a"), ("run-b", "pair-b")):
        result = controller.run_single(
            scenario=SCENARIO, application="blender", condition="baseline",
            workspace=workspace, baseline_home=tmp_path / "h1",
            optimized_home=tmp_path / "h2", baseline_profile="p",
            optimized_profile="p", output=output,
            run_id_override=run_id, pair_id_override=pair_id)
        assert result["certification_status"] == "TIMEOUT"
    root = tmp_path / "out"
    rec_a = _assert_terminal_record(
        root / "result-terminal-run-a-pair-a.json", status="TIMEOUT",
        run_id="run-a", pair_id="pair-a")
    rec_b = _assert_terminal_record(
        root / "result-terminal-run-b-pair-b.json", status="TIMEOUT",
        run_id="run-b", pair_id="pair-b")
    assert rec_a != rec_b
    assert sorted(p.name for p in root.glob("result-terminal-*.json")) == [
        "result-terminal-run-a-pair-a.json",
        "result-terminal-run-b-pair-b.json"]


def _raise_capture(exc):
    def raise_exc(*a, **k):
        raise exc
    return raise_exc


_LEAKY_ERROR_TEXT = (
    "prompt: do the thing | response: the result | api_key=secret-key "
    "| access_token=api-token | tokens_in=1234 tokens_out=5678 total=6912")


def test_run_single_failure_artifacts_do_not_leak_exception_text(monkeypatch, tmp_path):
    controller, workspace = _controller_env(monkeypatch, tmp_path)
    monkeypatch.setattr(controller, "preflight_codex",
                        lambda *a, **k: {"state": "READY_FOR_BENCHMARK",
                                         "errors": []})
    monkeypatch.setattr(controller, "capture_codex",
                        _raise_capture(CodexCaptureError(
                            _LEAKY_ERROR_TEXT,
                            evidence={"certification_status": "PROVIDER_USAGE_FAILED"})))
    output = tmp_path / "out" / "result.json"
    result = controller.run_single(
        scenario=SCENARIO, application="blender", condition="baseline",
        workspace=workspace, baseline_home=tmp_path / "h1",
        optimized_home=tmp_path / "h2", baseline_profile="p",
        optimized_profile="p", output=output,
        run_id_override="run-leak-1", pair_id_override="pair-leak-1")
    assert result["certification_status"] == "FAILED"
    assert result["failure_code"] == "capture_failed"
    assert result["evidence_available"] is True
    result_text = json.dumps(result)
    for leak in _LEAK_STRINGS:
        assert leak not in result_text
    terminal_path = tmp_path / "out" / "result-terminal-run-leak-1-pair-leak-1.json"
    ledger_path = tmp_path / "out" / "result-budget-ledger.json"
    terminal_text = terminal_path.read_text(encoding="utf-8")
    ledger_text = ledger_path.read_text(encoding="utf-8")
    for leak in _LEAK_STRINGS + ("1234", "5678", "6912"):
        assert leak not in terminal_text
        assert leak not in ledger_text
    record = _assert_terminal_record(terminal_path, status="FAILED",
                                     run_id="run-leak-1", pair_id="pair-leak-1")
    assert record["reason"] == "capture_failed"
    ledger = json.loads(ledger_text)
    assert ledger["certification_status"] == "FAILED"
    assert ledger["error"] == "capture_failed"


def _pilot_scenarios(controller, scenario):
    """Augmented scenario copies matching the entries built by _pilot_manifest."""
    base = dict(scenario, required_mcp_server="blender-mcp-server",
                oracle={"kind": "blender_scene_json", "expected": {}})
    second = dict(base, scenario_id=base["scenario_id"] + "-b")
    return [base, second]


def _pilot_manifest(controller, workspace, scenario):
    scenarios = _pilot_scenarios(controller, scenario)
    entries = []
    # Pilot requires exactly four sessions: two scenario entries x two conditions.
    for s in scenarios:
        for condition in ("baseline", "optimized"):
            run_id = "pilot-" + s["scenario_id"] + "-" + condition
            entry = {
                "application": "blender",
                "scenario_id": s["scenario_id"],
                "pair_id": controller._sha(s["scenario_id"]),
                "run_id": run_id,
                "repetition": 1,
                "condition": condition,
                "model": s["model"],
                "prompt_sha256": controller._sha(s["prompt"]),
                "expected_sha256": controller._sha(s["expected_exact"].strip()),
                "workspace_root": str(workspace.resolve()),
                "profile": "p",
                "expected_mcp_server": controller._expected_server(s, condition),
                "expected_mcp_tools": controller._expected_mcp_tools(s, condition),
                "oracle": controller._oracle_spec(s),
            }
            entries.append(entry)
    return {"schema": "pie-manifest-v1", "state": "FROZEN",
            "workspace_root": str(workspace.resolve()),
            "scenarios": entries}


def test_run_pilot_failure_artifacts_do_not_leak_exception_text(monkeypatch, tmp_path):
    controller, workspace = _controller_env(monkeypatch, tmp_path)
    monkeypatch.setattr(controller, "validate_manifest", lambda m: None)
    monkeypatch.setattr(controller, "validate_batch_budget", lambda m, k, n: None)
    monkeypatch.setattr(controller, "preflight_codex",
                        lambda *a, **k: {"state": "READY_FOR_BENCHMARK",
                                         "errors": []})
    monkeypatch.setattr(controller, "capture_codex",
                        _raise_capture(CodexCaptureError(
                            _LEAKY_ERROR_TEXT,
                            evidence={"certification_status": "PROVIDER_USAGE_FAILED"})))
    manifest = _pilot_manifest(controller, workspace, SCENARIO)
    scenarios = _pilot_scenarios(controller, SCENARIO)
    output = tmp_path / "out" / "pilot.json"
    result = controller.run_pilot(
        manifest=manifest, scenarios=scenarios, workspace=workspace,
        baseline_home=tmp_path / "h1", optimized_home=tmp_path / "h2",
        baseline_profile="p", optimized_profile="p", output=output,
        authorized_sessions=4)
    assert result["state"] == "AB_PILOT_FAILED"
    assert result["certification_status"] == "FAILED"
    failed = result["failed_execution"]
    assert failed["failure_code"] == "capture_failed"
    assert failed["evidence_available"] is True
    result_text = json.dumps(result)
    for leak in _LEAK_STRINGS:
        assert leak not in result_text
    terminal_paths = sorted((tmp_path / "out").glob("pilot-terminal-*.json"))
    assert len(terminal_paths) == 1
    terminal_text = terminal_paths[0].read_text(encoding="utf-8")
    ledger_path = tmp_path / "out" / "pilot-budget-ledger.json"
    ledger_text = ledger_path.read_text(encoding="utf-8")
    for leak in _LEAK_STRINGS + ("1234", "5678", "6912"):
        assert leak not in terminal_text
        assert leak not in ledger_text
    record = json.loads(terminal_text)
    assert record["status"] == "FAILED"
    assert record["reason"] == "capture_failed"
    ledger = json.loads(ledger_text)
    assert ledger["error"] == "capture_failed"
    assert ledger["certification_status"] == "FAILED"
