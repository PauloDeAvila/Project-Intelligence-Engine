"""Regression checks for the real-repository discovery laboratory."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pie_real_repo_lab import normalize_navigation_answer, benchmark_tasks, validate_gateway_base_url, require_gateway_secrets, normalize_usage, summarize_rows

class GatewayUrlValidation(unittest.TestCase):
    def test_loopback_http_is_accepted(self):
        self.assertTrue(validate_gateway_base_url("http://127.0.0.1:8000"))
        self.assertTrue(validate_gateway_base_url("http://localhost:8000"))
        self.assertTrue(validate_gateway_base_url("http://[::1]:8000"))
    def test_remote_https_is_accepted(self):
        self.assertTrue(validate_gateway_base_url("https://gateway.example.com/v1"))
    def test_remote_http_is_rejected(self):
        self.assertFalse(validate_gateway_base_url("http://gateway.example.com/v1"))
        self.assertFalse(validate_gateway_base_url("http://8.8.8.8:8000"))
    def test_missing_scheme_and_empty_are_rejected(self):
        self.assertFalse(validate_gateway_base_url("gateway.example.com/v1"))
        self.assertFalse(validate_gateway_base_url("ftp://gateway.example.com"))
        self.assertFalse(validate_gateway_base_url(""))
    def test_missing_api_key_is_rejected_even_for_valid_urls(self):
        with self.assertRaises(RuntimeError):require_gateway_secrets("https://gateway.example.com","")
        with self.assertRaises(RuntimeError):require_gateway_secrets("http://127.0.0.1:8000","")
        require_gateway_secrets("http://127.0.0.1:8000","secret-not-logged")

class UsageNormalization(unittest.TestCase):
    def test_complete_usage_is_available_with_tokens(self):
        self.assertEqual(
            normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}),
            {"provider_usage_status":"available","prompt_tokens":10,"completion_tokens":5,"total_tokens":15,
             "cached_input_tokens":None,"uncached_input_tokens":None})
    def test_top_level_cached_tokens_are_kept(self):
        out=normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15,"cached_input_tokens":4})
        self.assertEqual(out["provider_usage_status"],"available")
        self.assertEqual(out["cached_input_tokens"],4)
        self.assertEqual(out["uncached_input_tokens"],6)
    def test_nested_prompt_tokens_details_cache_is_used(self):
        out=normalize_usage({"prompt_tokens":10,"completion_tokens":5,
                             "prompt_tokens_details":{"cached_tokens":4}})
        self.assertEqual(out["provider_usage_status"],"available")
        self.assertEqual(out["cached_input_tokens"],4)
        self.assertEqual(out["uncached_input_tokens"],6)
    def test_top_level_cache_takes_precedence_over_nested_details(self):
        out=normalize_usage({"prompt_tokens":10,"completion_tokens":5,"cached_input_tokens":7,
                             "prompt_tokens_details":{"cached_tokens":4}})
        self.assertEqual(out["cached_input_tokens"],7)
        self.assertEqual(out["uncached_input_tokens"],3)
    def test_cache_absence_keeps_status_available_and_cache_none(self):
        out=normalize_usage({"prompt_tokens":10,"completion_tokens":5})
        self.assertEqual(out["provider_usage_status"],"available")
        self.assertIsNone(out["cached_input_tokens"])
        self.assertIsNone(out["uncached_input_tokens"])
    def test_non_dict_details_is_ignored(self):
        for details in ("x",4,None,True):
            out=normalize_usage({"prompt_tokens":10,"completion_tokens":5,
                                 "prompt_tokens_details":{"cached_tokens":4} if details is None else details})
            if details=="x" or details==4 or details is True:
                self.assertIsNone(out["cached_input_tokens"])
            self.assertEqual(out["provider_usage_status"],"available")
    def test_cache_equal_to_prompt_keeps_uncached_zero(self):
        out=normalize_usage({"prompt_tokens":10,"completion_tokens":5,"cached_input_tokens":10})
        self.assertEqual(out["provider_usage_status"],"available")
        self.assertEqual(out["cached_input_tokens"],10)
        self.assertEqual(out["uncached_input_tokens"],0)
    def test_cache_greater_than_prompt_is_unavailable_and_stays_none(self):
        for usage in ({"prompt_tokens":10,"completion_tokens":5,"cached_input_tokens":11},
                      {"prompt_tokens":10,"completion_tokens":5,
                       "prompt_tokens_details":{"cached_tokens":12}}):
            out=normalize_usage(usage)
            self.assertEqual(out["provider_usage_status"],"unavailable")
            self.assertIsNone(out["prompt_tokens"])
            self.assertIsNone(out["completion_tokens"])
            self.assertIsNone(out["total_tokens"])
            self.assertIsNone(out["cached_input_tokens"])
            self.assertIsNone(out["uncached_input_tokens"])
    def test_total_tokens_may_be_absent(self):
        out=normalize_usage({"prompt_tokens":10,"completion_tokens":5})
        self.assertEqual(out["provider_usage_status"],"available")
        self.assertEqual(out["prompt_tokens"],10)
        self.assertEqual(out["completion_tokens"],5)
        self.assertIsNone(out["total_tokens"])
    def test_missing_usage_is_unavailable_and_stays_none(self):
        for usage in ({},{},None,"x"):
            out=normalize_usage(usage)
            self.assertEqual(out["provider_usage_status"],"unavailable")
            self.assertIsNone(out["prompt_tokens"])
            self.assertIsNone(out["completion_tokens"])
            self.assertIsNone(out["total_tokens"])
            self.assertIsNone(out["cached_input_tokens"])
            self.assertIsNone(out["uncached_input_tokens"])
    def test_partial_usage_is_unavailable_and_stays_none(self):
        out=normalize_usage({"prompt_tokens":10})
        self.assertEqual(out["provider_usage_status"],"unavailable")
        self.assertIsNone(out["prompt_tokens"])
        self.assertIsNone(out["completion_tokens"])
        out=normalize_usage({"completion_tokens":3})
        self.assertEqual(out["provider_usage_status"],"unavailable")
        self.assertIsNone(out["prompt_tokens"])
        self.assertIsNone(out["completion_tokens"])
    def test_invalid_usage_is_unavailable(self):
        for usage in ({"prompt_tokens":-1,"completion_tokens":5},
                      {"prompt_tokens":10,"completion_tokens":-1},
                      {"prompt_tokens":"10","completion_tokens":5},
                      {"prompt_tokens":True,"completion_tokens":5},
                      {"prompt_tokens":10.0,"completion_tokens":5},
                      {"prompt_tokens":10,"completion_tokens":5,"total_tokens":-1},
                      {"prompt_tokens":10,"completion_tokens":5,"total_tokens":"15"},
                      {"prompt_tokens":10,"completion_tokens":5,"cached_input_tokens":-1},
                      {"prompt_tokens":10,"completion_tokens":5,"cached_input_tokens":"20"},
                      {"prompt_tokens":10,"completion_tokens":5,"cached_input_tokens":True},
                      {"prompt_tokens":10,"completion_tokens":5,"cached_input_tokens":2.0},
                      {"prompt_tokens":10,"completion_tokens":5,"prompt_tokens_details":{"cached_tokens":"20"}},
                      {"prompt_tokens":10,"completion_tokens":5,"prompt_tokens_details":{"cached_tokens":-3}}):
            out=normalize_usage(usage)
            self.assertEqual(out["provider_usage_status"],"unavailable")
            self.assertIsNone(out["prompt_tokens"])
            self.assertIsNone(out["completion_tokens"])
            self.assertIsNone(out["total_tokens"])
            self.assertIsNone(out["cached_input_tokens"])
            self.assertIsNone(out["uncached_input_tokens"])

class ModeSummaryAggregation(unittest.TestCase):
    def row(self,**kw):
        base={"model":"m","mode":"baseline","ok":True,"correct":False,"evidence_hit":True,
              "provider_usage_status":"available","prompt_tokens":0,"completion_tokens":0,
              "total_tokens":0,"cached_input_tokens":None,"uncached_input_tokens":None,"seconds":1.0}
        base.update(kw);return base
    def test_full_usage_sums_tokens(self):
        rows=[self.row(prompt_tokens=10,completion_tokens=5,total_tokens=15,seconds=1.0),
              self.row(prompt_tokens=20,completion_tokens=7,total_tokens=27,seconds=3.0)]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertEqual(s["prompt_tokens"],30)
        self.assertEqual(s["completion_tokens"],12)
        self.assertEqual(s["total_tokens"],42)
        self.assertEqual(s["median_latency_s"],2.0)
    def test_successful_call_without_usage_makes_totals_none_not_zero(self):
        rows=[self.row(prompt_tokens=10,completion_tokens=5,total_tokens=15),
              self.row(provider_usage_status="unavailable",prompt_tokens=None,completion_tokens=None,total_tokens=None)]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"missing")
        self.assertIsNone(s["prompt_tokens"])
        self.assertIsNone(s["completion_tokens"])
        self.assertIsNone(s["total_tokens"])
    def test_failed_calls_never_become_zero_and_do_not_block_ok(self):
        ok=self.row(prompt_tokens=10,completion_tokens=5,total_tokens=15)
        failed=dict(ok,ok=False,provider_usage_status="unavailable",prompt_tokens=None,completion_tokens=None,total_tokens=None)
        s=summarize_rows([ok,failed])
        self.assertEqual(s["successful"],1)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertEqual(s["prompt_tokens"],10)
        self.assertEqual(s["completion_tokens"],5)
        self.assertEqual(s["total_tokens"],15)
        all_failed=[dict(failed,ok=False) for _ in range(2)]
        s=summarize_rows(all_failed)
        self.assertEqual(s["successful"],0)
        self.assertEqual(s["provider_usage_status"],"missing")
        self.assertIsNone(s["prompt_tokens"])
    def test_no_calls_reports_no_calls(self):
        s=summarize_rows([])
        self.assertEqual(s["provider_usage_status"],"no_calls")
        self.assertIsNone(s["prompt_tokens"])
    def test_full_usage_from_provider_sums_all_fields(self):
        rows=[self.row(**normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15})),
              self.row(**normalize_usage({"prompt_tokens":20,"completion_tokens":7,"total_tokens":27}))]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertEqual(s["prompt_tokens"],30)
        self.assertEqual(s["completion_tokens"],12)
        self.assertEqual(s["total_tokens"],42)
    def test_absent_total_tokens_does_not_raise_and_keeps_total_none(self):
        rows=[self.row(**normalize_usage({"prompt_tokens":10,"completion_tokens":5})),
              self.row(**normalize_usage({"prompt_tokens":20,"completion_tokens":7}))]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertEqual(s["prompt_tokens"],30)
        self.assertEqual(s["completion_tokens"],12)
        self.assertIsNone(s["total_tokens"])
    def test_mixed_total_presence_yields_none_total_but_sums_prompt_and_completion(self):
        rows=[self.row(**normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15})),
              self.row(**normalize_usage({"prompt_tokens":20,"completion_tokens":7}))]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertEqual(s["prompt_tokens"],30)
        self.assertEqual(s["completion_tokens"],12)
        self.assertIsNone(s["total_tokens"])
    def test_partial_success_usage_is_missing_and_totals_none(self):
        rows=[self.row(**normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15})),
              self.row(**normalize_usage({"prompt_tokens":20}))]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"missing")
        self.assertIsNone(s["prompt_tokens"])
        self.assertIsNone(s["completion_tokens"])
        self.assertIsNone(s["total_tokens"])
    def test_cache_presence_sums_cached_and_uncached(self):
        rows=[self.row(**normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15,"cached_input_tokens":4})),
              self.row(**normalize_usage({"prompt_tokens":20,"completion_tokens":7,"total_tokens":27,"cached_input_tokens":8}))]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertEqual(s["cached_input_tokens"],12)
        self.assertEqual(s["uncached_input_tokens"],18)
    def test_mixed_cache_presence_yields_none_cache_sums_but_ok(self):
        rows=[self.row(**normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15,"cached_input_tokens":4})),
              self.row(**normalize_usage({"prompt_tokens":20,"completion_tokens":7,"total_tokens":27}))]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertIsNone(s["cached_input_tokens"])
        self.assertIsNone(s["uncached_input_tokens"])
    def test_absent_cache_keeps_cache_sums_none_but_ok(self):
        rows=[self.row(**normalize_usage({"prompt_tokens":10,"completion_tokens":5,"total_tokens":15})),
              self.row(**normalize_usage({"prompt_tokens":20,"completion_tokens":7,"total_tokens":27}))]
        s=summarize_rows(rows)
        self.assertEqual(s["provider_usage_status"],"ok")
        self.assertIsNone(s["cached_input_tokens"])
        self.assertIsNone(s["uncached_input_tokens"])
    def test_scheme_is_recorded_in_summary(self):
        rows=[self.row()]
        s=summarize_rows(rows,host="gateway.example.com",scheme="https")
        self.assertEqual(s["host"],"gateway.example.com")
        self.assertEqual(s["scheme"],"https")
        s=summarize_rows(rows,host="127.0.0.1",scheme="http")
        self.assertEqual(s["host"],"127.0.0.1")
        self.assertEqual(s["scheme"],"http")
    def test_scheme_defaults_to_none(self):
        self.assertIsNone(summarize_rows([self.row()])["scheme"])
        self.assertIsNone(summarize_rows([self.row()])["host"])

class RealRepoLabTests(unittest.TestCase):
    def test_path_line_reference_normalized_without_changing_symbol(self):
        self.assertEqual(
            normalize_navigation_answer({"path":"rich/live.py:278","symbol":"Live.process_renderables"}),
            {"path":"rich/live.py","symbol":"Live.process_renderables","symbol_brackets_normalized":False})
        self.assertEqual(
            normalize_navigation_answer({"path":"### rich/segment.py:520-534","symbol":"Segment.align_middle"}),
            {"path":"rich/segment.py","symbol":"Segment.align_middle","symbol_brackets_normalized":False})
    def test_invalid_answer_cannot_be_scored(self):
        self.assertEqual(normalize_navigation_answer({"path":4,"symbol":"ok"}),{})
        self.assertEqual(normalize_navigation_answer(None),{})
    def test_unwrapped_symbol_is_returned_unchanged(self):
        out=normalize_navigation_answer({"path":"rich/live.py:278","symbol":"Live.process_renderables"})
        self.assertEqual(out["symbol"],"Live.process_renderables")
        self.assertIs(out["symbol_brackets_normalized"],False)
    def test_single_outer_bracket_pair_is_stripped_once(self):
        for symbol,expected in (
            ("[Live.process_renderables]","Live.process_renderables"),
            ("(Live.process_renderables)","Live.process_renderables"),
            ("{Live.process_renderables}","Live.process_renderables")):
            out=normalize_navigation_answer({"path":"rich/live.py:278","symbol":symbol})
            self.assertEqual(out["symbol"],expected)
            self.assertIs(out["symbol_brackets_normalized"],True)
            self.assertEqual(out["path"],"rich/live.py")
    def test_nested_balanced_pair_is_stripped_once(self):
        out=normalize_navigation_answer({"path":"rich/live.py:278","symbol":"(f(x))"})
        self.assertEqual(out["symbol"],"f(x)")
        self.assertIs(out["symbol_brackets_normalized"],True)
    def test_ambiguous_or_inner_wrappers_are_not_silently_fixed(self):
        for symbol in ("[[x]","[a]b]","[Live.process_renderables]]","Live.process_renderables]"):
            out=normalize_navigation_answer({"path":"rich/live.py:278","symbol":symbol})
            self.assertEqual(out["symbol"],symbol)
            self.assertIs(out["symbol_brackets_normalized"],False)
    def test_cross_type_inner_delimiters_are_rejected(self):
        # A single depth counter would accept these; matching must be by type.
        for symbol in ("[foo{bar]","[foo}bar]","[foo(bar]","[foo)bar]","(foo[bar)","(foo]bar)",
                       "{foo[bar}","{foo]bar}","[foo{bar}baz]x]"):
            out=normalize_navigation_answer({"path":"rich/live.py:278","symbol":symbol})
            self.assertEqual(out["symbol"],symbol)
            self.assertIs(out["symbol_brackets_normalized"],False)
    def test_nested_matching_type_pairs_are_still_stripped(self):
        for symbol,expected in (("[foo{bar}baz]","foo{bar}baz"),("(f[x]g)","f[x]g"),
                                ("{a(b)c}","a(b)c")):
            out=normalize_navigation_answer({"path":"rich/live.py:278","symbol":symbol})
            self.assertEqual(out["symbol"],expected)
            self.assertIs(out["symbol_brackets_normalized"],True)
    def test_path_is_never_bracket_stripped(self):
        out=normalize_navigation_answer({"path":"[rich/live.py]:278","symbol":"Live.process_renderables"})
        self.assertEqual(out["path"],"[rich/live.py]")
        self.assertEqual(out["symbol"],"Live.process_renderables")
    def test_generated_tasks_are_seeded_and_deduplicated_by_file(self):
        rows=[{"path":f"rich/m{i}.py","symbol":f"f{i}","sentence":"This is a detailed implementation description."} for i in range(20)]
        a=benchmark_tasks(rows,12,412)
        b=benchmark_tasks(rows,12,412)
        self.assertEqual(a,b)
        self.assertEqual(len({t["oracle"]["path"] for t in a}),12)
    def test_not_enough_real_modules_fails(self):
        rows=[{"path":"rich/a.py","symbol":"a","sentence":"A lengthy description of the function."}]
        with self.assertRaises(RuntimeError):benchmark_tasks(rows,3,123)

if __name__=="__main__":unittest.main()
