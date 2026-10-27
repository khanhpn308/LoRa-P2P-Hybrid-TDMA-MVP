#!/usr/bin/env python3
"""MCP stdio smoke: negotiate protocol, list exact tools, reject invalid issue."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters

EXPECTED = {"harness_preflight", "harness_status", "harness_verify_candidate"}


async def test(server: Path) -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(server)])
    async with Client(params) as client:
        listed = await client.list_tools()
        names = {item.name for item in listed.tools}
        if names != EXPECTED:
            raise RuntimeError("Unexpected MCP tool surface")
        result = await client.call_tool("harness_preflight", {"issue_number": 0})
        if result.is_error:
            raise RuntimeError("Negative MCP call returned protocol/tool error")
        structured = result.structured_content
        # Different SDK serializer modes may wrap a dictionary result.
        text = json.dumps(structured, ensure_ascii=True) if structured is not None else " ".join(
            getattr(content, "text", "") for content in result.content
        )
        if '"BLOCKED"' not in text and "BLOCKED" not in text:
            raise RuntimeError("Invalid issue was not rejected")
    print(json.dumps({"status": "MCP_STDIO_SMOKE_PASS",
                      "negotiation": "PASS", "tools": sorted(names),
                      "invalid_issue_rejected": True}))


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise RuntimeError("Expected exactly one reviewed server path")
        asyncio.run(asyncio.wait_for(test(Path(sys.argv[1]).resolve(strict=True)), 25))
    except BaseException:
        print("MCP_STDIO_SMOKE_BLOCKED", file=sys.stderr)
        raise SystemExit(1)
