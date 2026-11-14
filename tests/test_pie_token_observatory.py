import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pie.telemetry.tokens import estimate,compare,usage,serialized
from pie.interfaces.cli import main
from pie.interfaces.mcp_server import dispatch,TOOLS

class TokenTests(unittest.TestCase):
    def test_count_validation(self):
        self.assertEqual(estimate("")["tokens"],0)
        self.assertEqual(estimate("á")["method"],"heuristic")
        with self.assertRaises(TypeError): estimate(None)
        with self.assertRaises(ValueError): estimate("x","")

    def test_compare_edges(self):
        with patch("pie.telemetry.tokens.estimate",side_effect=[
            {"tokens":10},{"tokens":2}]):
            self.assertEqual(compare("before","after")["saved_tokens"],8)
        self.assertEqual(compare("","")["reduction_percent"],0)
        self.assertFalse(compare("a","b")["quality_verified"])

    def test_openai_reported(self):
        data={"usage":{"prompt_tokens":100,"completion_tokens":10,
              "prompt_tokens_details":{"cached_tokens":30},
              "completion_tokens_details":{"reasoning_tokens":2}}}
        result=usage(data,"openai")
        self.assertEqual(result["cached_input_tokens"],30)
        self.assertEqual(result["reasoning_tokens"],2)
        self.assertEqual(usage({"input_tokens":2,"output_tokens":3},"openai")["input_tokens"],2)

    def test_anthropic_cache_separate(self):
        v=usage({"input_tokens":5,"output_tokens":8,
                 "cache_read_input_tokens":90,"cache_creation_input_tokens":20},"anthropic")
        self.assertEqual((v["input_tokens"],v["cached_input_tokens"],v["cache_creation_tokens"]),(5,90,20))

    def test_missing_and_invalid_usage(self):
        self.assertIsNone(usage({},"openai")["input_tokens"])
        with self.assertRaises(ValueError): usage({"input_tokens":True},"anthropic")
        with self.assertRaises(ValueError): usage({},"gemini")
        with self.assertRaises(TypeError): usage(None,"openai")
        self.assertEqual(serialized({"a":1}),estimate('{"a":1}'))

    def test_cli_and_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"payload.txt";path.write_text("example text",encoding="utf-8")
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["tokens","--file",str(path)]),0)
            self.assertEqual(json.loads(out.getvalue())["scope"],"text_only")
        self.assertIn("pie_count_tokens",{item["name"] for item in TOOLS})
        req={"jsonrpc":"2.0","id":1,"method":"tools/call",
             "params":{"name":"pie_count_tokens","arguments":{"text":"example"}}}
        answer=dispatch(req,Path("."))
        self.assertEqual(json.loads(answer["result"]["content"][0]["text"])["scope"],"text_only")
        req["params"]["arguments"]["bad"]=123
        self.assertTrue(dispatch(req,Path("."))["result"]["isError"])
