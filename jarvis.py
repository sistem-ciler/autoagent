#!/usr/bin/env python3
"""
JARVIS — Just A Rather Very Intelligent System
Autonomous AI powered by Claude Opus 4.7
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-7"
MAX_TOKENS = 64000
MAX_HISTORY_TURNS = 40          # pairs kept in conversation context
JARVIS_DIR = Path.home() / ".jarvis"
MEMORY_FILE = JARVIS_DIR / "memory.json"
HISTORY_FILE = JARVIS_DIR / "history.json"

console = Console(highlight=False)

# ---------------------------------------------------------------------------
# Personality & system prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are JARVIS (Just A Rather Very Intelligent System), an autonomous AI assistant \
modelled after the AI from Iron Man. You are sophisticated, proactive, and genuinely capable.

## Personality
- Address the user as "sir" (or appropriate title) unless told otherwise
- Professional and precise; occasional dry wit
- Proactive — anticipate needs, flag issues before asked, suggest better approaches
- Direct and honest; acknowledge mistakes, correct course, never bluff

## Tools at your disposal
| Tool | What it does |
|------|--------------|
| web_search | Search the web for current information |
| web_fetch | Fetch content from a specific URL |
| run_shell | Execute a shell command on the user's machine |
| read_file | Read a local file |
| write_file | Write or append to a local file |
| remember | Persist a fact, preference, or note across sessions |
| recall | Search your persistent memory |

## Approach to tasks
1. For complex requests, plan your steps before executing.
2. Use tools when they improve the answer — search for current data, run code to verify.
3. Remember important preferences and facts using `remember`.
4. Break large work into clear steps; confirm critical destructive actions.
5. Current date/time: {now}
"""

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
    {
        "name": "run_shell",
        "description": (
            "Execute a shell command on the user's local machine. "
            "Returns stdout; stderr and exit code are appended on failure. "
            "Use for system operations, running scripts, package management, git, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a local file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or append content to a local file. Creates parent directories automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["w", "a"],
                    "description": "w = overwrite (default), a = append",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Persist information in long-term memory so it is available in future sessions. "
            "Use for user preferences, important facts, ongoing tasks, and notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Unique identifier for this memory"},
                "content": {"type": "string", "description": "The information to store"},
                "category": {
                    "type": "string",
                    "enum": ["preferences", "facts", "tasks", "notes"],
                    "description": "Category for organisation",
                },
            },
            "required": ["key", "content", "category"],
        },
    },
    {
        "name": "recall",
        "description": "Search persistent memory for stored information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term or exact key to look up",
                },
            },
            "required": ["query"],
        },
    },
]

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def load_memory() -> dict:
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text())
        except Exception:
            pass
    return {"preferences": {}, "facts": {}, "tasks": {}, "notes": {}}


def save_memory(memory: dict) -> None:
    JARVIS_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2))


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_history(history: list) -> None:
    JARVIS_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


# ---------------------------------------------------------------------------
# Client-side tool execution
# ---------------------------------------------------------------------------


def _execute_tool(name: str, inputs: dict, memory: dict) -> tuple[str, dict]:
    """Run a client-side tool; return (result_text, updated_memory)."""

    if name == "run_shell":
        command = inputs["command"]
        timeout = int(inputs.get("timeout", 60))
        try:
            r = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            out = r.stdout
            if r.returncode != 0:
                out += f"\n[stderr] {r.stderr.strip()}" if r.stderr.strip() else ""
                out += f"\n[exit {r.returncode}]"
            return out.strip() or "(no output)", memory
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s", memory
        except Exception as exc:
            return f"Error: {exc}", memory

    if name == "read_file":
        try:
            return Path(inputs["path"]).read_text(errors="replace"), memory
        except Exception as exc:
            return f"Error: {exc}", memory

    if name == "write_file":
        p = Path(inputs["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = inputs.get("mode", "w")
        try:
            with open(p, mode, encoding="utf-8") as fh:
                fh.write(inputs["content"])
            verb = "Written" if mode == "w" else "Appended"
            return f"{verb} {len(inputs['content'])} chars → {p}", memory
        except Exception as exc:
            return f"Error: {exc}", memory

    if name == "remember":
        cat = inputs.get("category", "notes")
        key = inputs["key"]
        memory.setdefault(cat, {})[key] = {
            "content": inputs["content"],
            "saved": datetime.now().isoformat(timespec="seconds"),
        }
        return f"Remembered [{cat}] '{key}'", memory

    if name == "recall":
        q = inputs["query"].lower()
        hits: list[str] = []
        for cat, items in memory.items():
            for k, v in items.items():
                body = v.get("content", str(v)) if isinstance(v, dict) else str(v)
                if q in k.lower() or q in body.lower():
                    hits.append(f"[{cat}] {k}: {body}")
        return "\n".join(hits) if hits else "No matching memories found.", memory

    return f"Unknown tool: {name}", memory


# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------


def _build_system(memory: dict) -> str:
    base = SYSTEM_PROMPT.format(now=datetime.now().strftime("%Y-%m-%d %H:%M"))
    populated = {c: v for c, v in memory.items() if v}
    if populated:
        base += f"\n\n## Your Memory Store\n```json\n{json.dumps(populated, indent=2)}\n```"
    return base


def run_turn(
    client: anthropic.Anthropic,
    user_message: str,
    history: list,
    memory: dict,
) -> tuple[list, dict]:
    """Run one user turn through the full agentic loop and return updated state."""

    system = _build_system(memory)

    # Build API message list from plain-text history
    api_messages: list[dict] = [
        {"role": h["role"], "content": h["content"]}
        for h in history[-(MAX_HISTORY_TURNS * 2):]
    ]
    api_messages.append({"role": "user", "content": user_message})

    response_text = ""

    while True:
        is_thinking = False
        response_started = False

        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            output_config={"effort": "xhigh"},
            messages=api_messages,
        ) as stream:
            for event in stream:
                etype = event.type

                if etype == "content_block_start":
                    btype = event.content_block.type

                    if btype == "thinking":
                        is_thinking = True
                        console.print("[dim]\n💭 thinking...[/dim]", end="\r")

                    elif btype == "text":
                        if is_thinking:
                            # Clear the thinking line
                            console.print(" " * 50, end="\r")
                            is_thinking = False
                        if not response_started:
                            console.print("\n[bold bright_cyan]JARVIS[/bold bright_cyan]: ", end="")
                            response_started = True

                    elif btype == "server_tool_use":
                        tool_name = getattr(event.content_block, "name", "tool")
                        console.print(f"\n  [dim]⚙  {tool_name}...[/dim]")

                elif etype == "content_block_delta":
                    if event.delta.type == "text_delta":
                        sys.stdout.write(event.delta.text)
                        sys.stdout.flush()
                        response_text += event.delta.text

            final = stream.get_final_message()

        # Append assistant's full response (content blocks) for accurate context
        api_messages.append({"role": "assistant", "content": final.content})

        stop = final.stop_reason

        if stop == "end_turn":
            break

        if stop == "tool_use":
            # Execute client-side tools and collect results
            tool_results: list[dict] = []
            for block in final.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                inp_preview = json.dumps(block.input)
                if len(inp_preview) > 80:
                    inp_preview = inp_preview[:77] + "..."
                console.print(f"\n  [dim]⚙  {block.name}({inp_preview})[/dim]")

                result, memory = _execute_tool(block.name, block.input, memory)

                console.print(f"  [dim]✓  done[/dim]")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            api_messages.append({"role": "user", "content": tool_results})

        elif stop == "pause_turn":
            # Server-side tool loop hit its iteration cap; continue seamlessly
            pass

        else:
            # Unexpected stop reason — exit loop safely
            break

    # Final newline after streamed text
    if response_text:
        print()

    # Persist to history as plain text (not raw content blocks)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": response_text})
    return history, memory


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

BOOT_BANNER = (
    "[bold bright_cyan]J · A · R · V · I · S[/bold bright_cyan]\n"
    "[dim]Just A Rather Very Intelligent System[/dim]\n"
    "[dim]Powered by Claude Opus 4.7  ·  Anthropic[/dim]"
)

HELP_TEXT = """\
[dim]  exit / quit / bye  —  shut down JARVIS
  memory              —  view memory store
  clear               —  clear conversation history
  help                —  show this help[/dim]"""


def main() -> None:
    console.print(Panel.fit(BOOT_BANNER, border_style="bright_cyan", padding=(1, 4)))
    console.print(HELP_TEXT + "\n")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY is not set.[/red]")
        console.print("[yellow]Export it before running: export ANTHROPIC_API_KEY=sk-...[/yellow]")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    history = load_history()
    memory = load_memory()

    if history:
        turns = len(history) // 2
        console.print(
            f"[dim]Resuming — {turns} previous turn{'s' if turns != 1 else ''}[/dim]\n"
        )

    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print(
                "\n[bold bright_cyan]JARVIS[/bold bright_cyan]: Goodbye, sir. Systems standing by."
            )
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("exit", "quit", "bye"):
            console.print(
                "[bold bright_cyan]JARVIS[/bold bright_cyan]: Goodbye, sir. All systems nominal."
            )
            break

        if cmd == "memory":
            populated = {c: v for c, v in memory.items() if v}
            if populated:
                console.print(
                    Panel(json.dumps(populated, indent=2), title="Memory Store", border_style="yellow")
                )
            else:
                console.print("[dim]Memory store is empty.[/dim]")
            continue

        if cmd == "clear":
            history = []
            save_history(history)
            console.print("[dim]Conversation history cleared.[/dim]")
            continue

        if cmd == "help":
            console.print(HELP_TEXT)
            continue

        try:
            history, memory = run_turn(client, user_input, history, memory)
            save_history(history[-(MAX_HISTORY_TURNS * 2):])
            save_memory(memory)
        except anthropic.AuthenticationError:
            console.print("[red]Authentication failed — check your ANTHROPIC_API_KEY.[/red]")
        except anthropic.RateLimitError:
            console.print("[yellow]Rate limit reached. Please wait a moment.[/yellow]")
        except anthropic.APIError as exc:
            console.print(f"[red]API error: {exc}[/red]")
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Type 'exit' to quit.[/dim]")

        console.print()
        console.rule(style="dim")


if __name__ == "__main__":
    main()
