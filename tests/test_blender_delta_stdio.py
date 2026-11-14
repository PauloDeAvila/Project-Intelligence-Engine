"""Real JSON-RPC stdio regression using a mocked Blender MCP upstream."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class BlenderDeltaTransportTest(unittest.TestCase):
    def test_three_observations_with_manual_edit_between_calls(self):
        upstream = r'''
import json,sys
n=0
for line in sys.stdin:
    q=json.loads(line)
    if "id" not in q:
        continue
    method=q.get("method")
    if method=="initialize":
        result={"protocolVersion":"2025-03-26","capabilities":{"tools":{}},
                "serverInfo":{"name":"mock-blender","version":"2.2.9"}}
    elif method=="tools/list":
        result={"tools":[{"name":"get_scene_info","inputSchema":{"type":"object"}},
                         {"name":"execute_blender_code","inputSchema":{"type":"object"}}]}
    elif method=="tools/call" and q.get("params",{}).get("name")=="execute_blender_code":
        code=q["params"]["arguments"]["code"]
        if "PIE_SCENE_SNAPSHOT_V1" not in code:
            result={"isError":True,"content":[{"type":"text","text":"unexpected script"}]}
        else:
            n+=1
            material={"name":"Steel","metallic":0.9,
                      "nodes":[{"name":"Principled BSDF","inputs":{"Roughness":0.35 if n<3 else 0.28}}],
                      "links":[]}
            snapshot={"schema":"pie-blender-scene-snapshot-v1","scene":"Scene",
                      "scope":"selected","complete":True,
                      "omissions":{"objects":0,"materials":0},
                      "objects":[{"name":"Cube","type":"MESH"}],
                      "materials":[material]}
            result={"content":[{"type":"text","text":"Code executed successfully: PIE_SCENE_SNAPSHOT_V1="+json.dumps(snapshot)}]}
    else:
        result={}
    print(json.dumps({"jsonrpc":"2.0","id":q["id"],"result":result}),flush=True)
'''
        requests = [
            {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}},
            {"jsonrpc":"2.0","method":"notifications/initialized"},
            {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}},
            *[{"jsonrpc":"2.0","id":i,"method":"tools/call",
               "params":{"name":"pie_blender_scene_delta",
                         "arguments":{"scope":"selected","max_chars":3000}}}
              for i in (3,4,5)],
        ]
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        run=subprocess.run(
            [sys.executable, "-m", "pie.integrations.blender_mcp_bridge",
             "--max-chars", "1000", "--", sys.executable, "-c", upstream],
            input="\n".join(json.dumps(item) for item in requests)+"\n",
            text=True, capture_output=True, env=env, timeout=25,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        messages={item["id"]:item for item in (json.loads(s) for s in run.stdout.splitlines())}
        tools=[item["name"] for item in messages[2]["result"]["tools"]]
        self.assertIn("pie_blender_scene_delta", tools)
        result=[json.loads(messages[n]["result"]["content"][0]["text"]) for n in (3,4,5)]
        self.assertEqual([x["state"] for x in result], ["INITIAL","UNCHANGED","DELTA"])
        self.assertEqual(result[2]["materials"]["counts"]["changed"],1)
        self.assertIn("nodes", result[2]["materials"]["changed"][0]["details"])


if __name__=="__main__":
    unittest.main()
