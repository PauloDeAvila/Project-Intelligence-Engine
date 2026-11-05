"""Minimal MCP stdio server, JSON-RPC 2.0, no third-party runtime dependency.

Supports MCP initialize, tools/list, tools/call and ping with newline-delimited
stdio; requests never execute arbitrary shell commands.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pie.graph.relationships import build_relationships, get_relationships
from pie.retrieval.task_memory import start_task, record_task, resume_task
from pie.retrieval.task_search import search_tasks
from pie.retrieval.output_pipeline import compact_output, recover_output
from pie.interfaces.mcp_context import MCPContextEngine
from pie.retrieval.context import build_context
from pie.interfaces.cli import command_status, command_search, command_symbol
from pie.retrieval.symbols import analysis_summary, find_definitions, find_references
from pie.retrieval.evidence import build_evidence
from pie.retrieval.context_pack import build_context_pack

TOOLS = [
    {'name':'pie_output_compact','description':'RTK-inspired: redact, deduplicate and bound a tool log; save the sanitized full output for recovery. Text is limited to 4096 chars via MCP.', 'inputSchema':{'type':'object','properties':{'text':{'type':'string'},'kind':{'type':'string','enum':['log','test','git','terminal','web','api']},'max_chars':{'type':'integer','minimum':256,'maximum':64000},'exit_code':{'type':'integer','minimum':-65535,'maximum':65535}},'required':['text'],'additionalProperties':False}},
    {'name':'pie_output_get','description':'Recover the complete SANITIZED tool output by its opaque local ID.', 'inputSchema':{'type':'object','properties':{'output_id':{'type':'string'}},'required':['output_id'],'additionalProperties':False}},
    {'name':'pie_task_search', 'description':'Search project-local task memories by lexical terms; all entries are agent-supplied unverified claims, with source references.', 'inputSchema':{'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':20},'max_chars':{'type':'integer','minimum':1000,'maximum':64000}},'required':['query'],'additionalProperties':False}},
    {'name':'pie_task_start', 'description':'Start an explicit project-scoped persistent task; records only the supplied objective.', 'inputSchema':{'type':'object','properties':{'objective':{'type':'string'}},'required':['objective'],'additionalProperties':False}},
    {'name':'pie_task_record', 'description':'Atomically append an explicit action, decision, result, checkpoint or note; optionally change task status.', 'inputSchema':{'type':'object','properties':{'task_id':{'type':'string'},'kind':{'type':'string','enum':['action','decision','result','checkpoint','note']},'text':{'type':'string'},'reference':{'type':'string'},'status':{'type':'string','enum':['in_progress','blocked','completed']}},'required':['task_id','kind','text'],'additionalProperties':False}},
    {'name':'pie_task_resume', 'description':'Recover latest unfinished or blocked task, or one by ID, from project-local SQLite; bounded event history.', 'inputSchema':{'type':'object','properties':{'task_id':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':100}},'additionalProperties':False}},
    {'name':'pie_query', 'description':'Preferred unified source-grounded lookup: responsibilities, symbol/file navigation and verified impact relationships. Use this before direct file browsing.', 'inputSchema':{'type':'object','properties':{'query':{'type':'string'},'mode':{'type':'string','enum':['responsibility','navigation','impact']},'limit':{'type':'integer','minimum':1,'maximum':20},'max_chars':{'type':'integer','minimum':500,'maximum':200000}},'required':['query'],'additionalProperties':False}},
    {'name':'pie_verified_evidence', 'description':'Canonical hash-verified function or qualified method signature (e.g. MeasurementCache.get) and bounded verified direct call sites; rejects ambiguous or stale evidence.', 'inputSchema':{'type':'object','properties':{'symbol':{'type':'string'}},'required':['symbol'],'additionalProperties':False}},
    {'name':'pie_build_context_pack', 'description':'Deterministic v2 Context Pack for an exact function or qualified method (e.g. MeasurementCache.get); separates returned verified-call completeness from partial static coverage; never certifies exhaustive callers or runtime breakage.', 'inputSchema':{'type':'object','properties':{'symbol':{'type':'string'},'max_chars':{'type':'integer','minimum':1500,'maximum':64000},'max_calls':{'type':'integer','minimum':1,'maximum':100}},'required':['symbol'],'additionalProperties':False}},
    {'name':'pie_project_status', 'description':'Read index freshness and inventory.', 'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
    {'name':'pie_search_symbols', 'description':'Find indexed symbols by name.', 'inputSchema':{'type':'object','properties':{'query':{'type':'string'}},'required':['query'],'additionalProperties':False}},
    {'name':'pie_inspect_symbol', 'description':'Inspect symbol source locations.', 'inputSchema':{'type':'object','properties':{'name':{'type':'string'}},'required':['name'],'additionalProperties':False}},
    {'name':'pie_build_graph', 'description':'Rebuild static Python call/import edges from CURRENT indexed files.', 'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
    {'name':'pie_relationships', 'description':'Read evidence-based relationships for a symbol or file.', 'inputSchema':{'type':'object','properties':{'name':{'type':'string'}},'required':['name'],'additionalProperties':False}},
    {'name':'pie_build_context', 'description':'Retrieve hash-verified source ranges for a task/symbol.', 'inputSchema':{'type':'object','properties':{'query':{'type':'string'},'max_chars':{'type':'integer','minimum':500,'maximum':200000}},'required':['query'],'additionalProperties':False}},
    {'name':'pie_find_definitions', 'description':'Locate every definition site of a variable, parameter, class or function, with scope and inferred type.', 'inputSchema':{'type':'object','properties':{'name':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':500}},'required':['name'],'additionalProperties':False}},
    {'name':'pie_find_references', 'description':'Reverse lookup: who reads, writes or imports a symbol. Returns consumers with evidence.', 'inputSchema':{'type':'object','properties':{'name':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':500}},'required':['name'],'additionalProperties':False}},
    {'name':'pie_analysis_summary', 'description':'Counts of definitions and references by kind, context and resolution verdict.', 'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
]


def dispatch(request: dict, root: Path, engine: MCPContextEngine | None = None) -> dict | None:
    if not isinstance(request, dict):
        return {'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Request must be an object'}}
    rid = request.get('id')
    method = request.get('method')
    if rid is None and isinstance(method, str) and method.startswith('notifications/'):
        return None
    try:
        if "jsonrpc" in request and request["jsonrpc"] != "2.0":
            raise ValueError("jsonrpc must be 2.0")
        if method == 'initialize':
            result = {'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'pie','version':'0.2.0-preview'}}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools':TOOLS}
        elif method == 'tools/call':
            params = request.get('params') or {}
            if not isinstance(params, dict):
                raise ValueError('params must be an object')
            args = params.get('arguments', {})
            name = params.get('name')
            allowed = next((t for t in TOOLS if t['name']==name), None)
            if allowed is None:
                raise ValueError('Unknown tool')
            if not isinstance(args, dict):
                raise ValueError('arguments must be an object')
            if set(args) - set(allowed['inputSchema']['properties']):
                raise ValueError('Unknown arguments')
            if any(k not in args for k in allowed['inputSchema'].get('required', [])):
                raise ValueError('Missing required argument')
            for key, spec in allowed['inputSchema']['properties'].items():
                if key in args:
                    value = args[key]
                    if spec.get('type') == 'string' and not isinstance(value, str):
                        raise ValueError(f'{key} must be a string')
                    if spec.get('type') == 'string' and (len(value) > 4096 or not value.strip() or '\x00' in value):
                        raise ValueError(f'{key} must be a nonempty safe string <= 4096 chars')
                    if spec.get('type') == 'integer' and (type(value) is not int or not spec.get('minimum', -10**30) <= value <= spec.get('maximum', 10**30)):
                        raise ValueError(f'{key} must be an integer within range')
            if name == 'pie_task_record' and 'kind' in args and args['kind'] not in ('action','decision','result','checkpoint','note'):
                raise ValueError('Invalid event kind')
            if 'status' in args and args['status'] not in ('in_progress','blocked','completed'):
                raise ValueError('Invalid task status')
            if 'mode' in args and args['mode'] not in ('responsibility','navigation','impact'):
                raise ValueError('Invalid mode')
            functions = {
                'pie_output_compact':lambda:compact_output(root,args['text'],kind=args.get('kind','log'),max_chars=args.get('max_chars',4000),exit_code=args.get('exit_code')),
                'pie_output_get':lambda:recover_output(root,args['output_id']),
                'pie_task_search':lambda:search_tasks(root,args['query'],limit=args.get('limit',10),max_chars=args.get('max_chars',12000)),
                'pie_task_start':lambda:start_task(root,args['objective']),
                'pie_task_record':lambda:record_task(root,args['task_id'],args['kind'],args['text'],reference=args.get('reference'),status=args.get('status')),
                'pie_task_resume':lambda:resume_task(root,args.get('task_id'),args.get('limit',30)),
                'pie_query':lambda:engine.query(args['query'],mode=args.get('mode','responsibility'),limit=args.get('limit',5),max_chars=args.get('max_chars',12000)) if engine is not None else _standalone_query(root,args),
                'pie_verified_evidence':lambda:build_evidence(root,args['symbol']),
                'pie_build_context_pack':lambda:build_context_pack(root,args['symbol'],max_chars=args.get('max_chars',12000),max_calls=args.get('max_calls',100)),
                'pie_project_status':lambda:command_status(root),
                'pie_search_symbols':lambda:command_search(root,args['query']),
                'pie_inspect_symbol':lambda:command_symbol(root,args['name']),
                'pie_build_graph':lambda:build_relationships(root),
                'pie_relationships':lambda:get_relationships(root,args['name']),
                'pie_build_context':lambda:build_context(root,args['query'],args.get('max_chars',12000)),
                'pie_find_definitions':lambda:find_definitions(root,args['name'],args.get('limit',100)),
                'pie_find_references':lambda:find_references(root,args['name'],args.get('limit',100)),
                'pie_analysis_summary':lambda:analysis_summary(root),
            }
            result = {'content':[{'type':'text','text':json.dumps(functions[name](),ensure_ascii=False,separators=(',',':'))}]}
        else:
            return {'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}}
        return {'jsonrpc':'2.0','id':rid,'result':result}
    except Exception as exc:
        if method == 'tools/call':
            return {'jsonrpc':'2.0','id':rid,'result':{'content':[{'type':'text','text':str(exc)}],'isError':True}}
        return {'jsonrpc':'2.0','id':rid,'error':{'code':-32603,'message':str(exc)}}


def _standalone_query(root: Path, args: dict):
    with MCPContextEngine(root) as engine:
        return engine.query(args['query'], mode=args.get('mode','responsibility'), limit=args.get('limit',5), max_chars=args.get('max_chars',12000))


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path.cwd())
    configured_root = parser.parse_args(argv).root
    if configured_root.is_symlink():
        raise ValueError('MCP root must not be a symlink')
    root = configured_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('MCP root must be an existing directory')
    with MCPContextEngine(root) as engine:
      for line in sys.stdin:
        try:
            request = json.loads(line)
            if isinstance(request, dict) and request.get("jsonrpc") != "2.0":
                reply = {"jsonrpc": "2.0", "id": request.get("id"),
                         "error": {"code": -32600, "message": "Missing or invalid jsonrpc version"}}
            else:
                reply = dispatch(request,root,engine)
        except Exception as exc:
            reply = {'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':str(exc)}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply,ensure_ascii=False)+'\n')
            sys.stdout.flush()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
