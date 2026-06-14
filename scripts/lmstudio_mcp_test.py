#!/usr/bin/env python3
"""Drive adb-mcp via LM Studio OpenAI-compatible API for live device tests.

Usage
-----
    python scripts/lmstudio_mcp_test.py

Environment variables
---------------------
    LMSTUDIO_BASE_URL          LM Studio or Ollama OpenAI-compat base URL
    LMSTUDIO_MODEL             Model identifier (e.g. openai/gpt-oss-20b)
    LMSTUDIO_MAX_TIMEOUT_RETRIES
    LMSTUDIO_REQUEST_TIMEOUT_S
    MCP_TOOL_TIMEOUT_S
    BENCHMARK_TAGS             Comma-separated tag filter, e.g. "settings,apps"
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, TypeVar

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LM_BASE = os.environ.get("LMSTUDIO_BASE_URL", "http://106.101.7.27:1234/v1")
LM_MODEL = os.environ.get("LMSTUDIO_MODEL", "openai/gpt-oss-20b")
MAX_TOOL_ROUNDS = 15
MAX_TIMEOUT_RETRIES = int(os.environ.get("LMSTUDIO_MAX_TIMEOUT_RETRIES", "3"))
LM_REQUEST_TIMEOUT_S = float(os.environ.get("LMSTUDIO_REQUEST_TIMEOUT_S", "180"))
MCP_TOOL_TIMEOUT_S = float(os.environ.get("MCP_TOOL_TIMEOUT_S", "120"))
BENCHMARK_TAGS = set(os.environ.get("BENCHMARK_TAGS", "").lower().split(",")) - {""}

# ---------------------------------------------------------------------------
# System prompt — mirrors the copy-paste block in README § "System prompt"
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You control an Android device via ADB. Follow these rules exactly.

OBSERVATION
- Before acting, call get_screen(mode='text').
- The 'tree' field is a numbered list: "<id> [Class] \\"label\\"".
- Always act by id: tap(selector={"id": 12}).
- Prefer id > text > content_desc > resource_id > coordinates.

ACTING
- tap() and swipe() return screen_changed plus the new tree — no extra get_screen needed.
- If screen_changed is false, the action had no effect. Re-read and try a different selector.
- If the response contains truncated:true, swipe up/down to reveal more content.

SETTINGS & APP LAUNCH
- Android system settings: open_settings(panel='wifi' | 'bluetooth' | 'airplane_mode' | ...).
- To open an app: launch_app(app_name='Bixby'). Check foreground:true before continuing.
- To reach an app's own settings after launch: navigate_in_app_settings().

AMBIGUOUS SELECTOR
- If you get SELECTOR_AMBIGUOUS, read the 'candidates' list and re-tap by id.

GOAL CONFIRMATION
- Only report success after the desired state is visible in the returned screen tree.
- Never fabricate a result. If unsure, call get_screen and verify.
"""

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Benchmark prompt registry
# ---------------------------------------------------------------------------
# Each entry: (prompt_text, tags)
# Tags let you run subsets via BENCHMARK_TAGS env var.

_BENCHMARK: list[tuple[str, list[str]]] = [
    # ── Settings toggles ──────────────────────────────────────────────────
    (
        "Enable airplane mode.",
        ["settings", "toggle"],
    ),
    (
        "Disable airplane mode.",
        ["settings", "toggle"],
    ),
    (
        "Turn Wi-Fi off.",
        ["settings", "toggle"],
    ),
    (
        "Turn Wi-Fi back on.",
        ["settings", "toggle"],
    ),
    (
        "Toggle Bluetooth: if it is on turn it off, if it is off turn it on.",
        ["settings", "toggle"],
    ),
    # ── App launch ────────────────────────────────────────────────────────
    (
        "Open the Camera app.",
        ["apps", "launch"],
    ),
    (
        "Open the Settings app.",
        ["apps", "launch"],
    ),
    (
        "Open the Bixby app.",
        ["apps", "launch"],
    ),
    # ── In-app navigation ─────────────────────────────────────────────────
    (
        "Open the Bixby app and then open its Settings screen.",
        ["apps", "inapp"],
    ),
    (
        "Oeffne die Bixby App und oeffne die Einstellungen. "
        "Nutze navigate_in_app_settings nach dem Starten.",
        ["apps", "inapp", "german"],
    ),
    # ── Multi-step ────────────────────────────────────────────────────────
    (
        "Go to the Wi-Fi settings page and tell me the name of the first saved network, "
        "or say 'none saved' if there are no saved networks.",
        ["settings", "multistep"],
    ),
    (
        "Open the Display settings and find the screen timeout value currently set.",
        ["settings", "multistep"],
    ),
    (
        "Open the Clock app and navigate to the Alarm tab.",
        ["apps", "multistep"],
    ),
]


def _select_prompts() -> list[tuple[str, list[str]]]:
    if not BENCHMARK_TAGS:
        return _BENCHMARK
    return [(p, t) for p, t in _BENCHMARK if BENCHMARK_TAGS & set(t)]


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _safe_print(*parts: object, **kwargs) -> None:
    text = " ".join(str(p) for p in parts)
    end = kwargs.pop("end", "\n")
    flush = kwargs.pop("flush", False)
    try:
        print(text, end=end, flush=flush, **kwargs)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write(text.encode(enc, errors="replace") + end.encode(enc, errors="replace"))
        if flush:
            sys.stdout.flush()


class FatalTimeoutError(Exception):
    """Raised when an operation exceeds the retry limit; aborts the entire test run."""

    def __init__(self, label: str, attempts: int, cause: BaseException) -> None:
        self.label = label
        self.attempts = attempts
        self.cause = cause
        super().__init__(f"{label} timed out after {attempts} attempts")


async def _with_timeout_retries(
    label: str,
    operation: Callable[[], Awaitable[T]],
    timeout_s: float,
    max_retries: int = MAX_TIMEOUT_RETRIES,
) -> T:
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_s)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < max_retries:
                _safe_print(
                    f"  TIMEOUT: {label} (attempt {attempt}/{max_retries}), retrying...",
                    flush=True,
                )
            else:
                raise FatalTimeoutError(label, max_retries, exc) from exc
    raise FatalTimeoutError(label, max_retries, last_exc or asyncio.TimeoutError())  # pragma: no cover

def _tool_result_text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts) if parts else json.dumps({"content": str(result.content)})


def _mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in tools
    ]


async def run_prompt(
    client: httpx.AsyncClient,
    session: ClientSession,
    openai_tools: list[dict[str, Any]],
    prompt: str,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    tool_trace: list[dict[str, Any]] = []
    final_text = ""
    started = time.monotonic()

    for _ in range(MAX_TOOL_ROUNDS):
        payload = {
            "model": LM_MODEL,
            "messages": messages,
            "tools": openai_tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        resp = await _with_timeout_retries(
            "LM Studio chat/completions",
            lambda: client.post(
                f"{LM_BASE}/chat/completions",
                json=payload,
                timeout=LM_REQUEST_TIMEOUT_S,
            ),
            timeout_s=LM_REQUEST_TIMEOUT_S + 5,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]
        finish = choice.get("finish_reason")

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
        if message.get("tool_calls"):
            assistant_msg["tool_calls"] = message["tool_calls"]
        messages.append(assistant_msg)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            final_text = (message.get("content") or "").strip()
            elapsed = time.monotonic() - started
            return {
                "prompt": prompt,
                "finish_reason": finish,
                "tool_trace": tool_trace,
                "tool_calls": len(tool_trace),
                "elapsed_s": round(elapsed, 1),
                "final_response": final_text,
                "success": True,
            }

        for call in tool_calls:
            fn = call["function"]
            name = fn["name"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            result = await _with_timeout_retries(
                f"MCP tool {name}",
                lambda n=name, a=args: session.call_tool(n, arguments=a),
                timeout_s=MCP_TOOL_TIMEOUT_S,
            )
            text = _tool_result_text(result)
            tool_trace.append({"tool": name, "arguments": args, "result_preview": text[:2000]})

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": text,
                }
            )

    elapsed = time.monotonic() - started
    return {
        "prompt": prompt,
        "finish_reason": "max_tool_rounds",
        "tool_trace": tool_trace,
        "tool_calls": len(tool_trace),
        "elapsed_s": round(elapsed, 1),
        "final_response": final_text,
        "success": False,
    }


def _print_summary(results: list[dict[str, Any]], prompts: list[tuple[str, list[str]]]) -> None:
    """Print a benchmark summary table."""
    col_w = 52
    _safe_print("\n" + "=" * 80)
    _safe_print(f"BENCHMARK SUMMARY  model={LM_MODEL}")
    _safe_print("=" * 80)
    _safe_print(f"{'#':<3} {'Status':<7} {'Calls':>5} {'Time':>6}  {'Tags':<18}  Prompt")
    _safe_print("-" * 80)

    ok = 0
    total_calls = 0
    total_time = 0.0
    fatal = False

    for i, (r, (prompt, tags)) in enumerate(zip(results, prompts), 1):
        status = "OK" if r.get("success") else ("FATAL" if r.get("fatal") else "FAIL")
        calls = r.get("tool_calls", "-")
        elapsed = r.get("elapsed_s", "-")
        tag_str = ",".join(tags)[:18]
        prompt_short = prompt[:col_w].replace("\n", " ")

        _safe_print(f"{i:<3} {status:<7} {str(calls):>5} {str(elapsed) + 's':>6}  {tag_str:<18}  {prompt_short}")

        if r.get("success"):
            ok += 1
        if r.get("fatal"):
            fatal = True
        if isinstance(calls, int):
            total_calls += calls
        if isinstance(elapsed, float):
            total_time += elapsed

    _safe_print("-" * 80)
    _safe_print(
        f"Passed: {ok}/{len(results)}  |  "
        f"Total tool calls: {total_calls}  |  "
        f"Total time: {round(total_time, 1)}s"
    )
    if fatal:
        _safe_print("Run was aborted early due to repeated timeouts.")

    for r in results:
        if r.get("error"):
            _safe_print(f"  ERROR [{r['prompt'][:55]}]: {r['error']}")

    _safe_print("=" * 80)


async def main() -> int:
    _configure_stdio()
    repo = Path(__file__).resolve().parents[1]
    python = sys.executable
    server_module = "adb_mcp.__main__"

    server_params = StdioServerParameters(
        command=python,
        args=["-m", server_module],
        env=os.environ.copy(),
        cwd=str(repo),
    )

    selected = _select_prompts()
    if not selected:
        _safe_print("No prompts selected. Check BENCHMARK_TAGS.")
        return 1

    results: list[dict[str, Any]] = []

    async with AsyncExitStack() as stack:
        transport = await stack.enter_async_context(stdio_client(server_params))
        read, write = transport
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools_resp = await session.list_tools()
        openai_tools = _mcp_tools_to_openai(tools_resp.tools)
        _safe_print(f"Connected to adb-mcp ({len(openai_tools)} tools)")
        _safe_print(f"LM Studio: {LM_BASE}  model={LM_MODEL}")
        tag_filter = f"  tags={','.join(sorted(BENCHMARK_TAGS))}" if BENCHMARK_TAGS else ""
        _safe_print(f"Benchmark: {len(selected)} prompts{tag_filter}\n")

        async with httpx.AsyncClient() as client:
            for i, (prompt, tags) in enumerate(selected, 1):
                _safe_print("=" * 72)
                _safe_print(f"TEST {i}/{len(selected)} [{','.join(tags)}]")
                _safe_print(f"  {prompt}")
                _safe_print("=" * 72)
                try:
                    outcome = await run_prompt(client, session, openai_tools, prompt)
                    for step in outcome["tool_trace"]:
                        _safe_print(
                            f"  -> {step['tool']}({json.dumps(step['arguments'], ensure_ascii=False)})"
                        )
                        preview = step["result_preview"].replace("\n", " ")[:240]
                        _safe_print(f"     result: {preview}")
                    _safe_print(
                        f"\nFinal: {outcome['final_response'][:600] or '(no text -- tools only)'}"
                    )
                    _safe_print(
                        f"Status: {'OK' if outcome['success'] else 'INCOMPLETE'} | "
                        f"tool calls: {outcome.get('tool_calls', '?')} | "
                        f"time: {outcome.get('elapsed_s', '?')}s\n"
                    )
                    results.append(outcome)
                except FatalTimeoutError as exc:
                    err: dict[str, Any] = {
                        "prompt": prompt,
                        "error": str(exc),
                        "success": False,
                        "fatal": True,
                        "tool_calls": 0,
                        "elapsed_s": 0.0,
                    }
                    results.append(err)
                    _safe_print(f"FATAL TIMEOUT: {exc}\nStopping test run.\n", flush=True)
                    break
                except Exception as exc:
                    err = {
                        "prompt": prompt,
                        "error": str(exc),
                        "success": False,
                        "tool_calls": 0,
                        "elapsed_s": 0.0,
                    }
                    results.append(err)
                    _safe_print(f"ERROR: {exc}\n", flush=True)

    _print_summary(results, selected[: len(results)])

    fatal = any(r.get("fatal") for r in results)
    ok = sum(1 for r in results if r.get("success"))
    if fatal:
        return 2
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
