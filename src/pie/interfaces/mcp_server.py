"""Minimal MCP stdio server, JSON-RPC 2.0, no third-party runtime dependency.

Supports MCP initialize, tools/list, tools/call and ping with newline-delimited
stdio; requests never execute arbitrary shell commands.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pie.graph.relationships import build_relationships, get_relationships
from pie.interfaces.mcp_context import MCPContextEngine
from pie.retrieval.context import build_context
from pie.interfaces.cli import command_status, command_search, command_symbol
from pie.retrieval.symbols import analysis_summary, find_definitions, find_references

TOOLS = [
    {'name':'pie_query', 'description':'Preferred unified source-grounded lookup: responsibilities, symbol/file navigation and verified impact relationships. Use this before direct file browsing.', 'inputSchema':{'type':'object','properties':{'query':{'type':'string'},'mode':{'type':'string','enum':['responsibility','navigation','impact']},'limit':{'type':'integer','minimum':1,'maximum':20},'max_chars':{'type':'integer','minimum':500,'maximum':200000}},'required':['query'],'additionalProperties':False}},
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
    rid = request.get('id')
    method = request.get('method')
    if rid is None and isinstance(method, str) and method.startswith('notifications/'):
        return None
    try:
        if not isinstance(request, dict):
            raise ValueError('Request must be an object')
        if method == 'initialize':
            result = {'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'pie','version':'0.2.0-preview'}}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools':TOOLS}
        elif method == 'tools/call':
            params = request.get('params') or {}
            args = params.get('arguments') or {}
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
                    if spec.get('type') == 'integer' and (type(value) is not int or not spec.get('minimum', -10**30) <= value <= spec.get('maximum', 10**30)):
                        raise ValueError(f'{key} must be an integer within range')
            if 'mode' in args and args['mode'] not in ('responsibility','navigation','impact'):
                raise ValueError('Invalid mode')
            functions = {
                'pie_query':lambda:engine.query(args['query'],mode=args.get('mode','responsibility'),limit=args.get('limit',5),max_chars=args.get('max_chars',12000)) if engine is not None else _standalone_query(root,args),
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
            result = {'content':[{'type':'text','text':json.dumps(functions[name](),ensure_ascii=False)}]}
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
    root = parser.parse_args(argv).root.resolve()
    with MCPContextEngine(root) as engine:
      for line in sys.stdin:
        try:
            request = json.loads(line)
            reply = dispatch(request,root,engine)
        except Exception as exc:
            reply = {'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':str(exc)}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply,ensure_ascii=False)+'\n')
            sys.stdout.flush()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
