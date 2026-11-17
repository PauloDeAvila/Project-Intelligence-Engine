import json

from pie.certification.codex_isolation import isolated_codex_home


def test_isolated_home_contains_only_selected_server_and_cleans_up(tmp_path):
    (tmp_path / "config.toml").write_text(
        'model = "gpt-test"\nmodel_reasoning_effort = "medium"\n\n'
        '[mcp_servers.keep]\ncommand = "python"\nargs = ["-m", "keep", "--workspace", "old"]\n\n'
        '[mcp_servers.other]\ncommand = "python"\n', encoding="utf-8")
    (tmp_path / "profile.config.toml").write_text(
        '[mcp_servers.keep.env]\nFLAG = "profile"\n', encoding="utf-8")
    (tmp_path / "auth.json").write_text('{"token":"secret"}', encoding="utf-8")

    with isolated_codex_home(tmp_path, profile="profile", server="keep",
                             model="gpt-test", runtime_env={"RUN": "1"},
                             workspace=tmp_path / "workspace") as home:
        config = json.loads(json.dumps(__import__("tomllib").loads(
            (home / "config.toml").read_text(encoding="utf-8"))))
        assert config["model_reasoning_effort"] == "medium"
        assert list(config["mcp_servers"]) == ["keep"]
        assert config["mcp_servers"]["keep"]["command"] == "python"
        assert config["mcp_servers"]["keep"]["env"] == {"FLAG": "profile", "RUN": "1"}
        assert config["mcp_servers"]["keep"]["args"][-1] == str(tmp_path / "workspace")
        assert (home / "auth.json").is_file()
    assert not home.exists()
