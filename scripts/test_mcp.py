"""Smoke-test the AdLoop MCP server over real stdio (no client library needed).

Spawns `python -m app.mcp_server`, performs the MCP handshake, lists tools, and calls
list_brands + critique_ad (the moat) against a real rendered ad. Prints PASS/FAIL.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AD = sys.argv[1] if len(sys.argv) > 1 else "output/creatives/b079b05611.png"


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp_server"],
        cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        return json.loads(line) if line.strip() else None

    ok = True
    try:
        # 1) initialize
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}})
        init = recv()
        assert init["result"]["serverInfo"]["name"] == "adloop", init
        print("initialize      ->", init["result"]["protocolVersion"], init["result"]["serverInfo"])

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})  # notification (no reply)

        # 2) tools/list
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tl = recv()
        names = [t["name"] for t in tl["result"]["tools"]]
        assert set(["list_brands", "strategize_brand", "critique_ad", "generate_campaign"]) <= set(names), names
        print("tools/list      ->", names)

        # 3) tools/call list_brands (free)
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_brands", "arguments": {}}})
        lb = recv()
        brands = json.loads(lb["result"]["content"][0]["text"])
        print(f"list_brands     -> {len(brands)} brand(s) in memory")

        # 4) tools/call critique_ad — the MOAT, one real qwen-vl call
        if Path(ROOT / AD).exists():
            send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                  "params": {"name": "critique_ad", "arguments": {
                      "image_path": AD, "headline": "Made for movement",
                      "tone": "warm, grounded", "palette": ["#A8C686", "#000"]}}})
            cr = recv()
            verdict = json.loads(cr["result"]["content"][0]["text"])
            print(f"critique_ad     -> overall {verdict.get('overall')}/100 · pass={verdict.get('pass')} · "
                  f"{len(verdict.get('required_changes', []))} fix(es)")
        else:
            print(f"critique_ad     -> skipped (no ad at {AD})")

        # 5) unknown tool → error surfaced in-band
        send({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
        er = recv()
        assert "error" in er, er
        print("unknown tool    -> error handled:", er["error"]["message"])

        print("\nMCP SERVER: PASS ✓")
    except Exception as e:
        ok = False
        print("\nMCP SERVER: FAIL ✗ ->", repr(e))
        print("stderr:\n", proc.stderr.read()[-1500:])
    finally:
        proc.terminate()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
