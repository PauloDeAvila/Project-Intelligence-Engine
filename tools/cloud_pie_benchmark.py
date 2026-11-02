#!/usr/bin/env python3
"""Cloud benchmark: baseline, current PIE, and hand-curated reference upper bound; no secrets in output."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships
from pie.retrieval.context import build_context
from pie_causal_selector import build_causal_context, render_control_flow
from rtk_style_context import compact_source_evidence
from pie_runtime_verifier import observe_case
from semantic_gate import verify_fields

LAB = {
"mini_order/__init__.py": "from .models import Order\nfrom .inventory import Inventory\nfrom .payment import PaymentGateway\nfrom .service import OrderService\n",
"mini_order/config.py": "MAX_RETRIES = 3\nRETRYABLE_ERRORS = frozenset({'temporary_failure'})\n",
"mini_order/models.py": "from dataclasses import dataclass\nfrom decimal import Decimal\n@dataclass(frozen=True)\nclass Order:\n    sku: str\n    quantity: int\n    unit_price: Decimal\n    @property\n    def total(self):\n        return self.unit_price * self.quantity\n",
"mini_order/inventory.py": "class InsufficientStock(Exception): pass\nclass Inventory:\n    def __init__(self, stock): self.stock = stock.copy()\n    def reserve(self, sku, quantity):\n        if quantity <= 0: raise ValueError('quantity must be positive')\n        if self.stock.get(sku, 0) < quantity: raise InsufficientStock(sku)\n        self.stock[sku] -= quantity\n    def release(self, sku, quantity):\n        self.stock[sku] = self.stock.get(sku, 0) + quantity\n",
"mini_order/payment.py": "from . import config\nclass PaymentError(Exception):\n    def __init__(self, code):\n        self.code = code\n        super().__init__(code)\nclass PaymentGateway:\n    def __init__(self, failures_before_success=0, failure_code='temporary_failure'):\n        self.failures_before_success = failures_before_success\n        self.failure_code = failure_code\n        self.calls = 0\n    def charge(self, amount):\n        self.calls += 1\n        if self.calls <= self.failures_before_success: raise PaymentError(self.failure_code)\n        return f'payment-{self.calls}'\ndef charge_with_retry(gateway, amount):\n    for attempt in range(config.MAX_RETRIES + 1):\n        try: return gateway.charge(amount)\n        except PaymentError as error:\n            if error.code not in config.RETRYABLE_ERRORS or attempt == config.MAX_RETRIES: raise\n    raise AssertionError('unreachable')\n",
"mini_order/service.py": "from .inventory import Inventory\nfrom .models import Order\nfrom .payment import PaymentGateway, charge_with_retry\nclass OrderService:\n    def __init__(self, inventory: Inventory, gateway: PaymentGateway):\n        self.inventory = inventory\n        self.gateway = gateway\n    def checkout(self, order: Order):\n        if order.unit_price <= 0: raise ValueError('unit_price must be positive')\n        self.inventory.reserve(order.sku, order.quantity)\n        try: return charge_with_retry(self.gateway, order.total)\n        except Exception:\n            self.inventory.release(order.sku, order.quantity)\n            raise\n",
"tests/test_checkout.py": "import unittest\nfrom decimal import Decimal\nfrom unittest.mock import patch\nfrom mini_order import Inventory, Order, OrderService, PaymentGateway\nfrom mini_order.payment import PaymentError\nclass Tests(unittest.TestCase):\n    def test_retry_limit(self):\n        gateway=PaymentGateway(failures_before_success=99)\n        with patch('mini_order.config.MAX_RETRIES', 2):\n            with self.assertRaises(PaymentError): OrderService(Inventory({'A':2}), gateway).checkout(Order('A',1,Decimal('5')))\n        self.assertEqual(gateway.calls,3)\n    def test_retry_success(self):\n        gateway=PaymentGateway(failures_before_success=2)\n        self.assertEqual(OrderService(Inventory({'A':2}),gateway).checkout(Order('A',1,Decimal('5'))),'payment-3')\n    def test_rollback_on_failure(self):\n        stock=Inventory({'A':2})\n        with self.assertRaises(PaymentError): OrderService(stock,PaymentGateway(failures_before_success=99)).checkout(Order('A',1,Decimal('5')))\n        self.assertEqual(stock.stock['A'],2)\n    def test_nonretryable_error(self):\n        gateway=PaymentGateway(failures_before_success=99,failure_code='declined')\n        with self.assertRaises(PaymentError): OrderService(Inventory({'A':2}),gateway).checkout(Order('A',1,Decimal('5')))\n        self.assertEqual(gateway.calls,1)\n",
}
QUESTIONS={
"MAX_RETRIES":"Se MAX_RETRIES mudar de 3 para 0, quantas vezes gateway.charge executa quando falha? O que ocorre em checkout e quais testes verificar?",
"release":"Se Inventory.release for removido, qual exceção acontece após uma falha de pagamento e o que ocorre à exceção original e ao estoque? Cite testes.",
"charge_with_retry":"Se charge_with_retry engolir PaymentError e retornar None, explique exatamente o retorno de checkout, o estado do estoque e os testes afetados."
}
RELEVANCE={
"MAX_RETRIES":[("mini_order/config.py",None),("mini_order/payment.py","charge_with_retry"),("mini_order/service.py","OrderService.checkout"),("tests/test_checkout.py","test_retry_limit"),("tests/test_checkout.py","test_rollback_on_failure")],
"release":[("mini_order/inventory.py","Inventory.release"),("mini_order/service.py","OrderService.checkout"),("mini_order/payment.py","charge_with_retry"),("tests/test_checkout.py","test_rollback_on_failure")],
"charge_with_retry":[("mini_order/payment.py","charge_with_retry"),("mini_order/service.py","OrderService.checkout"),("mini_order/inventory.py","Inventory.reserve"),("tests/test_checkout.py","test_rollback_on_failure"),("tests/test_checkout.py","test_nonretryable_error")],
}
SYSTEM=("Você analisa mudanças hipotéticas de código Python. Os arquivos mostrados representam o estado ANTES da alteração; simule o estado DEPOIS da alteração e siga o fluxo de chamadas, retornos, exceções e mutações. "
        "Diferencie retorno normal de exceção e exceção original de falha durante tratamento. Não invente arquivos, testes ou fatos ausentes. "
        "Responda apenas conforme o esquema de tipos solicitado no JSON.")

def source_slice(path, symbol):
    text=LAB[path]
    if symbol is None: return text
    tree=ast.parse(text)
    target=symbol.split('.')
    nodes=tree.body
    chosen=None
    for name in target:
        chosen=next((n for n in nodes if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name),None)
        if chosen is None and len(target)==1:
            matches=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
            if len(matches)==1:chosen=matches[0]
        if chosen is None: raise ValueError((path,symbol))
        nodes=chosen.body
    return '\n'.join(text.splitlines()[chosen.lineno-1:chosen.end_lineno])

def curated_context(case):
    parts=[]
    seen=set()
    for path,name in RELEVANCE[case]:
        snippet=source_slice(path,name)
        key=(path,hashlib.sha256(snippet.encode()).hexdigest())
        if key in seen: continue
        seen.add(key)
        parts.append(f"### {path} :: {name or 'module'}\n{snippet}")
    return '\n\n'.join(parts)

def compact_evidence(report):
    """Serialize only source-backed evidence with path/line provenance.

    Metadata remains in evidence.json for audit rather than repeated in prompts.
    """
    if report.get("context_state") not in ("CURRENT","PARTIAL"):
        raise RuntimeError(f"Causal context state={report.get('context_state')!r}; omitted={report.get('omitted',[])[:3]!r}")
    lines=[]
    seen=set()
    for e in report.get("evidence",[]):
        key=(e["path"],e["start_line"],e["end_line"])
        if key in seen:continue
        seen.add(key)
        lines.append(f"### {e['path']}:{e['start_line']}-{e['end_line']} [{e['kind']}]\n{e['content']}")
    return "\n\n".join(lines)


def compact_flow_evidence(report):
    code=compact_evidence(report)
    facts=render_control_flow(report)
    return code+("\n\n### Fluxo de controle inferido sintaticamente (não comprova despacho dinâmico)\n"+facts if facts else "")


def rtk_flow_evidence(report):
    result=compact_source_evidence(report,max_chars=12000)
    facts=render_control_flow(report)
    return result["content"]+("\n\nAST_CONTROL_FLOW (syntactic, not a runtime guarantee):\n"+facts if facts else "")


def baseline_context(root):
    return "\n\n".join(
        f"### {p.relative_to(root).as_posix()}\n{p.read_text(encoding='utf-8')}"
        for p in sorted(root.rglob("*.py")) if ".pie" not in p.parts
    )

def synthetic_modules(n):
    """Unrelated but plausible small Python modules for a transparent scaling stress test."""
    for i in range(n):
        lines=[f'"""Synthetic metrics module {i:03d}; not part of the order checkout pipeline."""',
               f'class MetricsBucket{i:03d}:',
               '    def __init__(self):',
               '        self.values = []',
               '    def record(self, value):',
               '        self.values.append(value)',
               '    def summarize(self):',
               '        if not self.values: return 0',
               '        return sum(self.values) / len(self.values)']
        for j in range(10):
            lines += [f'def transform_{i:03d}_{j:02d}(number):',
                      f'    scaled = number * {j+2} + {i%13}',
                      '    return (scaled // 2) if scaled > 100 else scaled']
        yield f"unrelated_metrics/module_{i:03d}.py", "\n".join(lines)+"\n"



# Controlled semantic ground truth for this synthetic laboratory.
# These assertions are independent of the LLM and apply identically to all modes.
ANSWER_KEYS={
    "MAX_RETRIES":{"attempts":1,"additional_retries":0,"rollback_on_payment_error":True,"error_type":"PaymentError"},
    "release":{"error_type":"AttributeError","original_error_masked":True,"stock_restored":False,"rollback_succeeds":False},
    "charge_with_retry":{"checkout_returns_none":True,"release_called":False,"stock_restored":False,"payment_error_propagates":False},
}
def evaluation_prompt(case):
    types={k:("boolean" if type(v) is bool else "integer" if type(v) is int else "string") for k,v in ANSWER_KEYS[case].items()}
    return (QUESTIONS[case]+"\nProduza apenas um objeto JSON válido, sem markdown, após simular a mudança. "
            "Tipos exatos por chave (isto NÃO contém valores corretos): "+json.dumps(types)+". "
            "Use true/false sem aspas para booleanos, números inteiros para contagens e strings para exceções. "
            "Não omita chaves nem substitua booleanos pelo valor numérico do estoque.")
def semantic_grade(case,answer):
    try:
        answer=answer.strip()
        if answer.startswith("```"):
            answer=answer.split("\n",1)[1].rsplit("```",1)[0].strip()
        parsed=json.loads(answer)
        if not isinstance(parsed,dict):raise ValueError("not object")
    except (ValueError,IndexError,TypeError):
        return {"passed":0,"total":len(ANSWER_KEYS[case]),"parseable":False,"by_field":{}}
    checks={name:type(parsed.get(name)) is type(expected) and parsed.get(name)==expected for name,expected in ANSWER_KEYS[case].items()}
    return {"passed":sum(checks.values()),"total":len(checks),"parseable":True,"by_field":checks}

def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def call(endpoint,key,model,prompt,max_tokens):
    payload={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":max_tokens,"stream":False}
    req=urllib.request.Request(endpoint.rstrip('/')+"/v1/chat/completions",data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=90) as response: data=json.load(response)
        choice=(data.get('choices') or [{}])[0]
        return {"ok":True,"seconds":round(time.perf_counter()-start,3),"answer":(choice.get("message") or {}).get("content") or "","finish_reason":choice.get("finish_reason"),"usage":data.get("usage",{}),"actual_model":data.get("model")}
    except urllib.error.HTTPError as e:
        return {"ok":False,"seconds":round(time.perf_counter()-start,3),"status":e.code,"error_category":"HTTP_ERROR"}
    except Exception as e:
        return {"ok":False,"seconds":round(time.perf_counter()-start,3),"error_category":type(e).__name__}

def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',default='gh/gpt-4o-mini')
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--max-tokens',type=int,default=768)
    parser.add_argument('--out',default='benchmark-results')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--scale-modules',type=int,default=0)
    parser.add_argument('--modes',default='baseline,pie_raw,pie_auto,pie_compact,pie_flow,pie_rtk,pie_rtk_flow,curated_reference')
    args=parser.parse_args()
    if not (1 <= args.repeats <= 10): parser.error('repeats 1..10')
    if not (0 <= args.scale_modules <= 150): parser.error('scale-modules 0..150')
    selected_modes=[mode.strip() for mode in args.modes.split(',')]
    valid_modes={'baseline','pie_raw','pie_auto','pie_compact','pie_flow','pie_rtk','pie_rtk_flow','curated_reference','baseline_observed','pie_observed'}
    if len(selected_modes)!=len(set(selected_modes)) or not selected_modes or not set(selected_modes)<=valid_modes: parser.error('Invalid or duplicate modes')
    endpoint=os.getenv('PIE_API_BASE_URL','').rstrip('/')
    key=os.getenv('PIE_API_KEY','')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for p,s in list(LAB.items())+list(synthetic_modules(args.scale_modules)):
            target=root/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(s,encoding='utf-8')
        tests=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-q"],cwd=root,env={**os.environ,"PYTHONPATH":str(root)},capture_output=True,text=True,timeout=30)
        if tests.returncode != 0: raise RuntimeError("Lab regression tests failed before model inference")
        print("Lab regression tests: PASS")
        index_started=time.perf_counter()
        idx=index_project(root)
        index_seconds=round(time.perf_counter()-index_started,5)
        if idx.get('index_state')!='CURRENT': raise RuntimeError('PIE index not current')
        rel=build_relationships(root)
        print('Static relationships built:',rel.get('stored',rel.get('relations_observed','unknown')))
        retrieval_started=time.perf_counter()
        # Reuse a single hash-verified causal retrieval per question.
        causal_reports={}
        causal_retrieval_seconds={}
        for question in QUESTIONS:
            retrieval_begin=time.perf_counter()
            causal_reports[question]=build_causal_context(root,question,max_chars=12000)
            causal_retrieval_seconds[question]=round(time.perf_counter()-retrieval_begin,6)
        contexts={
            "baseline":{q:baseline_context(root) for q in QUESTIONS},
            "pie_raw":{q:json.dumps(build_context(root,q,max_chars=12000),ensure_ascii=False) for q in QUESTIONS},
            "pie_auto":{q:json.dumps(causal_reports[q],ensure_ascii=False) for q in QUESTIONS},
            "pie_compact":{q:compact_evidence(causal_reports[q]) for q in QUESTIONS},
            "pie_flow":{q:compact_flow_evidence(causal_reports[q]) for q in QUESTIONS},
            "pie_rtk":{q:compact_source_evidence(causal_reports[q],max_chars=12000)["content"] for q in QUESTIONS},
            "pie_rtk_flow":{q:rtk_flow_evidence(causal_reports[q]) for q in QUESTIONS},
            "curated_reference":{q:curated_context(q) for q in QUESTIONS},
        }
        # An executable fixture is an independent evidence source, not an LLM oracle.
        observed={name:observe_case(root,name) for name in QUESTIONS}
        for name,actual in observed.items():
            if actual != ANSWER_KEYS[name]:
                raise RuntimeError("Ground-truth drift: runtime verification disagrees with expected schema for "+name)
        contexts["baseline_observed"]={name:contexts["baseline"][name]+"\n\nEXECUTION OBSERVATION (post-mutation, isolated fixture):\n"+json.dumps(observed[name],sort_keys=True) for name in QUESTIONS}
        contexts["pie_observed"]={name:contexts["pie_rtk_flow"][name]+"\n\nEXECUTION OBSERVATION (post-mutation, isolated fixture):\n"+json.dumps(observed[name],sort_keys=True) for name in QUESTIONS}
        retrieval_seconds=round(time.perf_counter()-retrieval_started,5)
        checks={
          "MAX_RETRIES":["range(config.MAX_RETRIES + 1)","self.inventory.release(","test_retry_limit"],
          "release":["def release(","except Exception:","test_rollback_on_failure"],
          "charge_with_retry":["def charge_with_retry(","self.inventory.reserve(","test_rollback_on_failure"]
        }
        audit={}
        for mode in contexts:
            audit[mode]={}
            for q,c in contexts[mode].items():
                audit[mode][q]={"chars":len(c),"sha256":sha(c),"missing":[term for term in checks[q] if term not in c]}
        (out/"evidence.json").write_text(json.dumps({"audit":audit,"questions":QUESTIONS,"contexts":contexts,"index_seconds":index_seconds,"retrieval_seconds_all_contexts":retrieval_seconds,"causal_retrieval_seconds_by_question":causal_retrieval_seconds},ensure_ascii=False,indent=2),encoding='utf-8')
        if any(audit["curated_reference"][q]["missing"] for q in QUESTIONS):raise RuntimeError("Curated context insufficient")
        if any(audit["pie_auto"][q]["missing"] for q in QUESTIONS):raise RuntimeError("Automatic causal context insufficient; no inference will run")
        if any(audit["pie_compact"][q]["missing"] for q in QUESTIONS):raise RuntimeError("Compact causal context insufficient; no inference will run")
        if any(audit["pie_flow"][q]["missing"] for q in QUESTIONS):raise RuntimeError("Control-flow context insufficient; no inference will run")
        if any(audit["pie_rtk"][q]["missing"] for q in QUESTIONS):raise RuntimeError("RTK-style adapter context insufficient; no inference will run")
        if any(audit["pie_rtk_flow"][q]["missing"] for q in QUESTIONS):raise RuntimeError("RTK + AST context insufficient; no inference will run")
        if any(audit["pie_observed"][q]["missing"] for q in QUESTIONS):raise RuntimeError("PIE runtime-evidence context insufficient")
        if args.dry_run:
            print('DRY RUN PASSED:',json.dumps({q:{m:audit[m][q]['chars'] for m in contexts} for q in QUESTIONS}));return
        if not (endpoint.startswith('https://') and key):raise RuntimeError('Missing HTTPS endpoint or inference secret')
        jobs=[]
        for rep in range(args.repeats):
            cases=list(QUESTIONS);random.Random(101+rep).shuffle(cases)
            for q in cases:
                modes=list(selected_modes)
                random.Random(202+rep+len(q)).shuffle(modes)
                jobs.extend((rep,q,m) for m in modes)
        for i,(rep,q,mode) in enumerate(jobs,1):
            context=contexts[mode][q]
            response=call(endpoint,key,args.model,"Pergunta: "+evaluation_prompt(q)+"\n\nCódigo e evidências:\n"+context,args.max_tokens)
            entry={"repeat":rep,"case":q,"mode":mode,"context_chars":len(context),"context_hash":sha(context),**response}
            if response["ok"]:entry["semantic_grade"]=semantic_grade(q,response["answer"])
            if response["ok"] and mode in ("pie_observed","baseline_observed"):
                entry["certification"]=verify_fields(response["answer"],observed[q])
            results.append(entry)
            (out/"results.json").write_text(json.dumps({"schema":1,"model":args.model,"results":results},ensure_ascii=False,indent=2),encoding="utf-8")
            print(f"{i}/{len(jobs)} {q} {mode} {'OK' if response['ok'] else 'FAIL'} {response['seconds']}s",flush=True)
            if not response["ok"]:break
            time.sleep(.5)
    summary={}
    for mode in selected_modes:
        vals=[r for r in results if r["mode"]==mode and r["ok"]]
        summary[mode]={"n":len(vals),"median_latency_s":round(statistics.median([x["seconds"] for x in vals]),3) if vals else None,"total_tokens":sum(x.get("usage",{}).get("total_tokens",0) for x in vals),"prompt_tokens":sum(x.get("usage",{}).get("prompt_tokens",0) for x in vals),"completion_tokens":sum(x.get("usage",{}).get("completion_tokens",0) for x in vals),"nonstop":sum(x.get("finish_reason")!="stop" for x in vals),"correct_fields":sum(x.get("semantic_grade",{}).get("passed",0) for x in vals),"total_fields":sum(x.get("semantic_grade",{}).get("total",0) for x in vals),"certified_answers":sum(x.get("certification",{}).get("approved",False) for x in vals)}
    (out/"summary.json").write_text(json.dumps({"model":args.model,"scale_modules":args.scale_modules,"modes":selected_modes,"cases":list(QUESTIONS),"summary":summary,"verification_mode":"post-mutation isolated execution observations are included identically for both observed variants; this is not a blind LLM test","index_seconds_one_time":index_seconds,"retrieval_seconds_all_contexts":retrieval_seconds,"causal_retrieval_seconds_by_question":causal_retrieval_seconds,"grading":"Deterministic JSON-field scoring against known behavior of the synthetic mini-order lab; not a general code-correctness metric.","caveat":"The curated reference uses case-specific source selection; it is NOT a general-purpose PIE algorithm. One small lab, no automated semantic grading, and no established speedup."},ensure_ascii=False,indent=2),encoding='utf-8')
    print("SUMMARY",json.dumps(summary))
    if len(results)!=len(jobs) or any(not r["ok"] for r in results):sys.exit(1)

if __name__=="__main__":run()
