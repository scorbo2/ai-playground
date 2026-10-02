#!/usr/bin/env python3
"""End-to-end tests for the docmgr MCP server.

Each scenario spawns the real script as a stdio MCP server (plus one
streamable-HTTP server) and drives it with a real MCP client session against
a throwaway fixture directory.

Run:  .venv/bin/python test_docmgr.py
"""

import asyncio
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

SCRIPT = Path(__file__).resolve().parent / "docmgr"

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    suffix = f"  [{detail}]" if detail and not condition else ""
    print(f"{status} {label}{suffix}")
    if not condition:
        FAILURES.append(label)


def text_of(result) -> str:
    return result.content[0].text if result.content else ""


def data_of(result):
    """Extract a tool result that carries structured data (list / dict / int).

    mcp 1.30+ FastMCP puts the typed result in structuredContent["result"]
    and may only put a lossy rendering in the text content, so prefer the
    structured channel when present.
    """
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured["result"]
    return json.loads(text_of(result))


def make_params(docs_dir: Path, *flags: str) -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[str(SCRIPT), *flags, str(docs_dir)])


async def with_session(params: StdioServerParameters, scenario, *scenario_args) -> None:
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            await scenario(session, init, *scenario_args)


def build_fixture(docs: Path, outside: Path) -> None:
    (docs / "hello.txt").write_text("Hello, world!\nMy fluffy bunny likes carrots.\n", encoding="utf-8")
    (docs / "notes").mkdir()
    (docs / "notes" / "ideas.txt").write_text("Project ideas: a fluffy bunny app.\n", encoding="utf-8")
    (docs / ".hidden.txt").write_text("hidden but served\n", encoding="utf-8")
    (docs / "unicode.txt").write_text("café au lait\n", encoding="utf-8")
    (docs / "empty.txt").write_text("", encoding="utf-8")
    (docs / "binary.bin").write_bytes(b"\x00\x01\xff\xfe\x02 binary \xff\x00")
    (outside / "secret.txt").write_text("secret data\n", encoding="utf-8")
    (docs / "escape.txt").symlink_to(outside / "secret.txt")


def fresh_fixture(base: Path, name: str) -> Path:
    docs = base / name
    outside = base / f"{name}-outside"
    docs.mkdir()
    outside.mkdir()
    build_fixture(docs, outside)
    return docs


FLAGS = ("--allow-edit", "--allow-create", "--allow-delete")


def instruction_flags(init) -> list[str]:
    """The permission flags named in the server instructions, if any."""
    text = init.instructions or ""
    return [flag for flag in FLAGS if flag in text]


async def scenario_read_only(session, init, docs: Path) -> None:
    # GIVEN the server runs with no permission flags,
    # THEN the read tools work, every write tool is refused, and the
    # instructions advertise all three write capabilities as disabled.

    check("read_only: instructions advertise all write capabilities as disabled",
          instruction_flags(init) == list(FLAGS), init.instructions or "<no instructions>")

    tools = await session.list_tools()
    names = sorted(t.name for t in tools.tools)
    check("read_only: all nine tools are advertised", names == sorted([
        "search_documents", "list_all_documents", "glob", "get_document",
        "get_document_length", "get_document_partial", "edit_document",
        "create_document", "delete_document",
    ]), str(names))

    r = await session.call_tool("list_all_documents", {})
    # Sorted rel_paths; binary.bin (non-UTF-8) and escape.txt (escaping
    # symlink) must be invisible; hidden file must be present.
    check("read_only: list_all_documents returns served docs sorted",
          data_of(r) == [".hidden.txt", "empty.txt", "hello.txt", "notes/ideas.txt", "unicode.txt"],
          str(data_of(r)))

    r = await session.call_tool("glob", {"path_str": "*.txt"})
    check("read_only: glob('*.txt') matches top-level txt files only",
          data_of(r) == [".hidden.txt", "empty.txt", "hello.txt", "unicode.txt"], str(data_of(r)))

    r = await session.call_tool("glob", {"path_str": "**/ideas.txt"})
    check("read_only: glob('**/ideas.txt') recurses", data_of(r) == ["notes/ideas.txt"], str(data_of(r)))

    hello = (docs / "hello.txt").read_text(encoding="utf-8")
    r = await session.call_tool("get_document", {"rel_path": "hello.txt"})
    check("read_only: get_document returns full content", text_of(r) == hello, text_of(r))

    r = await session.call_tool("get_document_length", {"rel_path": "unicode.txt"})
    # "café au lait\n" is 13 characters but 14 bytes — length must be in characters.
    check("read_only: get_document_length counts characters, not bytes",
          data_of(r) == 13 and (docs / "unicode.txt").stat().st_size == 14, str(data_of(r)))

    r = await session.call_tool("search_documents", {"query": "fluffy bunny"})
    hits = data_of(r)
    check("read_only: search finds both documents, sorted by rel_path",
          [h["rel_path"] for h in hits] == ["hello.txt", "notes/ideas.txt"], str(hits))
    expected_offset = hello.find("fluffy bunny")
    check("read_only: search reports the match offset", hits[0]["offset"] == expected_offset, str(hits[0]))
    check("read_only: search snippet brackets the match (up to 50 chars each side)",
          hits[0]["snippet"] == hello[max(0, expected_offset - 50):expected_offset + len("fluffy bunny") + 50]
          and hits[0]["snippet_offset"] == max(0, expected_offset - 50), str(hits[0]))

    r = await session.call_tool("search_documents", {"query": "FLUFFY BUNNY"})
    check("read_only: search is case-insensitive by default", len(data_of(r)) == 2, str(data_of(r)))

    r = await session.call_tool("search_documents", {"query": "FLUFFY BUNNY", "case_sensitive": True})
    check("read_only: case_sensitive search finds nothing", data_of(r) == [], str(data_of(r)))

    r = await session.call_tool("search_documents", {"query": "zzz-no-such-term"})
    check("read_only: search with no hits returns an empty list", data_of(r) == [])

    r = await session.call_tool("search_documents", {"query": "fluffy", "max_results": 1})
    check("read_only: max_results caps the number of hits", len(data_of(r)) == 1, str(data_of(r)))

    r = await session.call_tool("get_document_partial", {"rel_path": "hello.txt", "offset": 0, "length": 5})
    check("read_only: partial read from offset 0", text_of(r) == "Hello", text_of(r))

    r = await session.call_tool("get_document_partial", {"rel_path": "hello.txt", "offset": len(hello), "length": 0})
    check("read_only: offset at end of document with length 0 returns ''", text_of(r) == "", repr(text_of(r)))

    for args in (
        {"rel_path": "hello.txt", "offset": -1, "length": 5},
        {"rel_path": "hello.txt", "offset": len(hello) + 1, "length": 5},
        {"rel_path": "hello.txt", "offset": 0, "length": len(hello) + 1},
        {"rel_path": "hello.txt", "offset": 0, "length": -1},
    ):
        r = await session.call_tool("get_document_partial", args)
        check(f"read_only: invalid partial args are rejected {args}", r.isError, text_of(r))

    for rel_path in ("/etc/passwd", "../outside.txt", "notes/../hello.txt", "nope.txt", "binary.bin", "notes"):
        r = await session.call_tool("get_document", {"rel_path": rel_path})
        check(f"read_only: get_document rejects {rel_path!r}", r.isError, text_of(r))

    r = await session.call_tool("get_document", {"rel_path": "escape.txt"})
    check("read_only: symlink escaping the served directory is rejected", r.isError, text_of(r))

    for name, args in (
        ("edit_document", {"rel_path": "hello.txt", "to_replace": "x", "replace_with": "y", "offset": 0}),
        ("create_document", {"rel_path": "new.txt", "text": "x"}),
        ("delete_document", {"rel_path": "hello.txt"}),
    ):
        r = await session.call_tool(name, args)
        check(f"read_only: {name} is refused without its flag",
              r.isError and "not enabled" in text_of(r), text_of(r))


async def scenario_allow_all(session, init, docs: Path) -> None:
    # GIVEN the server runs with --allow-all,
    # THEN create/edit/delete all work, invalid edits are rejected, and the
    # instructions advertise all write capabilities as enabled.

    check("allow_all: instructions advertise all write capabilities as enabled",
          instruction_flags(init) == [] and (init.instructions or "").count("enabled") == 3,
          init.instructions or "<no instructions>")

    r = await session.call_tool("create_document", {"rel_path": "new/dir/file.txt", "text": "hello create"})
    check("allow_all: create_document creates nested directories",
          not r.isError and (docs / "new/dir/file.txt").read_text(encoding="utf-8") == "hello create",
          text_of(r))

    r = await session.call_tool("create_document", {"rel_path": "new/dir/file.txt", "text": "again"})
    check("allow_all: create_document refuses an existing path",
          r.isError and "already exists" in text_of(r), text_of(r))

    hello = (docs / "hello.txt").read_text(encoding="utf-8")
    offset = hello.find("carrots")
    r = await session.call_tool("edit_document",
                                {"rel_path": "hello.txt", "to_replace": "carrots", "replace_with": "peas", "offset": offset})
    expected = hello[:offset] + "peas" + hello[offset + len("carrots"):]
    check("allow_all: edit replaces at the given offset",
          not r.isError and (docs / "hello.txt").read_text(encoding="utf-8") == expected, text_of(r))

    r = await session.call_tool("edit_document",
                                {"rel_path": "hello.txt", "to_replace": "peas", "replace_with": "carrots",
                                 "offset": offset + 1})
    check("allow_all: edit rejects an offset where the text does not start", r.isError, text_of(r))

    r = await session.call_tool("edit_document",
                                {"rel_path": "empty.txt", "to_replace": "", "replace_with": "fresh", "offset": 0})
    check("allow_all: empty to_replace inserts at offset",
          (docs / "empty.txt").read_text(encoding="utf-8") == "fresh", text_of(r))

    r = await session.call_tool("get_document_length", {"rel_path": "empty.txt"})
    r = await session.call_tool("edit_document",
                                {"rel_path": "empty.txt", "to_replace": "", "replace_with": "\nappended",
                                 "offset": data_of(r)})
    check("allow_all: appending at offset == document length",
          (docs / "empty.txt").read_text(encoding="utf-8") == "fresh\nappended", text_of(r))

    r = await session.call_tool("delete_document", {"rel_path": "notes/ideas.txt"})
    check("allow_all: delete removes the document but keeps its directory",
          not r.isError and not (docs / "notes/ideas.txt").exists() and (docs / "notes").is_dir(), text_of(r))

    r = await session.call_tool("delete_document", {"rel_path": "notes/ideas.txt"})
    check("allow_all: deleting a missing document errors", r.isError, text_of(r))

    r = await session.call_tool("delete_document", {"rel_path": "notes"})
    check("allow_all: deleting a directory errors", r.isError, text_of(r))


async def scenario_permission_flags(session, init, allowed: str, docs: Path) -> None:
    # GIVEN the server runs with exactly one permission flag,
    # THEN the matching tool works and the other write tools are refused.
    tool_for = {
        "edit": ("edit_document",
                 {"rel_path": "empty.txt", "to_replace": "", "replace_with": "x", "offset": 0}),
        "create": ("create_document", {"rel_path": "perm.txt", "text": "x"}),
        "delete": ("delete_document", {"rel_path": "empty.txt"}),
    }

    name, args = tool_for[allowed]
    r = await session.call_tool(name, args)
    check(f"flag --allow-{allowed}: allowed tool works", not r.isError, text_of(r))

    for other in ("edit", "create", "delete"):
        if other == allowed:
            continue
        other_name, other_args = tool_for[other]
        r = await session.call_tool(other_name, other_args)
        check(f"flag --allow-{allowed}: {other_name} is refused",
              r.isError and "not enabled" in text_of(r), text_of(r))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f"server on {host}:{port} did not come up")


async def scenario_streamable_http(docs: Path) -> None:
    # GIVEN the server runs with --host,
    # THEN tools are callable over streamable HTTP.
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--host", "127.0.0.1", "--port", str(port), str(docs)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        await wait_for_port("127.0.0.1", port)
        # Browser clients (MCP Inspector) send a CORS preflight before the
        # real request; without Access-Control-Allow-* headers the browser
        # aborts with a NetworkError, so pin the preflight behavior too.
        import httpx
        async with httpx.AsyncClient() as client:
            preflight = await client.options(
                f"http://127.0.0.1:{port}/mcp",
                headers={
                    "Origin": "http://localhost:6274",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type, accept, mcp-session-id",
                },
            )
            check("http: CORS preflight on /mcp returns 2xx with allow-origin",
                  200 <= preflight.status_code < 300
                  and preflight.headers.get("access-control-allow-origin") in ("*", "http://localhost:6274"),
                  f"{preflight.status_code} {dict(preflight.headers)}")

            # Cross-origin JavaScript can only read "simple" response headers;
            # mcp-session-id must be explicitly exposed, or browser clients
            # (Inspector Direct mode) cannot learn the session ID from the
            # initialize response and die with "Missing session ID".
            init = await client.post(
                f"http://127.0.0.1:{port}/mcp",
                headers={
                    "Origin": "http://localhost:6274",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "e2e", "version": "0"}},
                },
            )
            exposed = init.headers.get("access-control-expose-headers", "").lower()
            check("http: initialize response exposes mcp-session-id to cross-origin JS",
                  bool(init.headers.get("mcp-session-id")) and "mcp-session-id" in exposed,
                  f"session-id={init.headers.get('mcp-session-id')!r} expose={exposed!r}")

        async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                r = await session.call_tool("get_document", {"rel_path": "hello.txt"})
                check("http: get_document works over streamable-http",
                      not r.isError and text_of(r) == (docs / "hello.txt").read_text(encoding="utf-8"),
                      text_of(r))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


async def amain() -> int:
    base = Path(tempfile.mkdtemp(prefix="docmgr-test-"))
    print(f"fixture root: {base}")
    try:
        print("== read_only (no permission flags) ==")
        docs = fresh_fixture(base, "read_only")
        await with_session(make_params(docs), scenario_read_only, docs)

        print("== --allow-all ==")
        docs = fresh_fixture(base, "allow_all")
        await with_session(make_params(docs, "--allow-all"), scenario_allow_all, docs)

        for flag in ("edit", "create", "delete"):
            print(f"== --allow-{flag} only ==")
            docs = fresh_fixture(base, f"allow_{flag}")
            await with_session(make_params(docs, f"--allow-{flag}"), scenario_permission_flags, flag, docs)

        print("== streamable-http ==")
        await scenario_streamable_http(fresh_fixture(base, "http"))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES:")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
