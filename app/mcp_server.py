"""
AdLoop MCP server — expose the agent society over the Model Context Protocol.

Any MCP client (Claude Desktop, an IDE, or another agent) can drive AdLoop as tools:
research a brand, generate a campaign, and — the moat — run the qwen-vl vision Critic to
SCORE any ad image 0-100 before a cent of ad spend.

Implemented as hand-rolled JSON-RPC 2.0 over newline-delimited stdio (zero dependencies).
The official MCP SDK requires Python 3.10+; this box runs 3.9, so the transport is
implemented directly against the spec. Only JSON-RPC responses go to stdout; logs → stderr.

Run:       python -m app.mcp_server
Register:  command="python", args=["-m","app.mcp_server"], cwd=<repo>  (see mcp.example.json)
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable, Optional

from . import memory
from .agents import critic, director, strategist

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "adloop", "version": "0.1.0"}


def _log(msg: str) -> None:
    print(f"[adloop-mcp] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- tool impls

def _t_list_brands(args: dict[str, Any]) -> Any:
    return [
        {"id": b.get("id"), "name": b.get("name"), "url": b.get("url"),
         "offering_type": b.get("offering_type")}
        for b in memory.list_brand_kits()
    ]


def _t_strategize(args: dict[str, Any]) -> Any:
    kit = strategist.run(args["url"], docs=args.get("description"), persist=True)
    return {"id": kit.get("id"), "name": kit.get("name"), "offering_type": kit.get("offering_type"),
            "tone": kit.get("tone"), "value_props": kit.get("value_props"), "palette": kit.get("palette")}


def _t_critique(args: dict[str, Any]) -> Any:
    brand: dict[str, Any] = {}
    if args.get("brand_kit_id"):
        brand = dict(memory.get_brand_kit(args["brand_kit_id"]) or {})
    for k in ("tone", "rules", "palette"):
        if args.get(k) is not None:
            brand[k] = args[k]
    brief = {"headline": args.get("headline", ""), "subhead": args.get("subhead", ""),
             "hook": args.get("hook", ""), "cta": args.get("cta", "")}
    return critic.review(args["image_path"], brief, brand)


def _t_generate(args: dict[str, Any]) -> Any:
    kit = memory.get_brand_kit(args["brand_kit_id"])
    if not kit:
        raise ValueError("unknown brand_kit_id (call list_brands or strategize_brand first)")
    creatives = director.run_campaign(
        kit, args["objective"], args.get("channel", "instagram"),
        int(args.get("n", 1)), int(args.get("max_rounds", 1)),
    )
    return [
        {"id": c["id"], "status": c["status"], "score": (c.get("scorecard") or {}).get("overall"),
         "headline": (c.get("brief") or {}).get("headline"), "image_path": c.get("image_path")}
        for c in creatives
    ]


TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_brands",
        "description": "List brands AdLoop has already researched and stored in memory (with their brand_kit_id).",
        "inputSchema": {"type": "object", "properties": {}},
        "_fn": _t_list_brands,
    },
    {
        "name": "strategize_brand",
        "description": ("Research a product/brand URL into a structured Brand Kit (name, tone, palette, "
                        "value props, rules) and persist it. Returns the brand_kit_id to use for generation."),
        "inputSchema": {"type": "object", "properties": {
            "url": {"type": "string", "description": "the brand or product page URL"},
            "description": {"type": "string", "description": "optional extra context to sharpen the brief"},
        }, "required": ["url"]},
        "_fn": _t_strategize,
    },
    {
        "name": "critique_ad",
        "description": ("THE MOAT: run the qwen-vl vision Critic on any ad image. Returns a 0-100 overall "
                        "score across 6 ad-craft dimensions (thumbstop, hierarchy, legibility, brand_fit, "
                        "hook_clarity, cta_visibility), a pass/fail, and concrete required changes — grade a "
                        "creative BEFORE ad spend. Give image_path plus optional brand context."),
        "inputSchema": {"type": "object", "properties": {
            "image_path": {"type": "string", "description": "path to the ad image to score"},
            "brand_kit_id": {"type": "string", "description": "optional: pull tone/rules/palette from a stored brand"},
            "headline": {"type": "string"}, "subhead": {"type": "string"},
            "hook": {"type": "string"}, "cta": {"type": "string"},
            "tone": {"type": "string"},
            "rules": {"type": "array", "items": {"type": "string"}},
            "palette": {"type": "array", "items": {"type": "string"}},
        }, "required": ["image_path"]},
        "_fn": _t_critique,
    },
    {
        "name": "generate_campaign",
        "description": ("Run the full agent society for a stored brand: copywriter → design researcher → "
                        "art director ↔ critic revise loop. Returns creatives with their critic scores. "
                        "Synchronous — can take a few minutes and consumes model/Apify credits."),
        "inputSchema": {"type": "object", "properties": {
            "brand_kit_id": {"type": "string"},
            "objective": {"type": "string"},
            "channel": {"type": "string", "description": "instagram | story | meta_feed"},
            "n": {"type": "integer", "description": "number of variants"},
            "max_rounds": {"type": "integer", "description": "max critic revision rounds per variant"},
        }, "required": ["brand_kit_id", "objective"]},
        "_fn": _t_generate,
    },
]
TOOL_MAP: dict[str, Callable[[dict[str, Any]], Any]] = {t["name"]: t["_fn"] for t in TOOLS}


def _public_tools() -> list[dict[str, Any]]:
    return [{k: v for k, v in t.items() if k != "_fn"} for t in TOOLS]


# ---------------------------------------------------------------- JSON-RPC

def _resp(rid: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _handle(req: dict[str, Any]) -> Optional[dict[str, Any]]:
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        return _resp(rid, {"protocolVersion": PROTOCOL_VERSION,
                           "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method in ("notifications/initialized", "initialized"):
        return None  # notification — no response
    if method == "ping":
        return _resp(rid, {})
    if method == "tools/list":
        return _resp(rid, {"tools": _public_tools()})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = TOOL_MAP.get(name)
        if fn is None:
            return _err(rid, -32602, f"unknown tool: {name}")
        try:
            result = fn(args)
            return _resp(rid, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                               "isError": False})
        except Exception as e:  # tool errors are reported IN the result, per MCP
            _log("tool error:\n" + traceback.format_exc())
            return _resp(rid, {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})

    if rid is not None:  # unknown request method
        return _err(rid, -32601, f"method not found: {method}")
    return None  # unknown notification — ignore


def main() -> None:
    memory.init_db()
    _log(f"AdLoop MCP server ready (stdio, protocol {PROTOCOL_VERSION}). {len(TOOLS)} tools.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
