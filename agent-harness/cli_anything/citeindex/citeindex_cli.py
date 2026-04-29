#!/usr/bin/env python3
"""cli-anything-citeindex — Stateful CLI harness for CiteIndex research infrastructure.

Usage:
    cli-anything-citeindex [OPTIONS] COMMAND [ARGS]...

Commands:
    project   Corpus management (new, info, validate, list)
    ingest    Ingest documents (file, url, crawl)
    search    Search corpus (query)
    chat      Chat with citations (ask, interactive)
    memory    Memory & history (search, list)
    export    Export & render (render, bibliography)
    session   Session management (save, load, undo, redo, status)
    repl      Interactive REPL mode

Every command supports --json for machine-readable output.
"""
from __future__ import annotations

import json
import sys
import os
from typing import Any, Optional

import click

from . import __version__
from .core.project import project_new, project_info, project_validate, project_list
from .core.ingest import ingest_file, ingest_url, ingest_crawl
from .core.search import search_query
from .core.chat import chat_ask
from .core.memory import memory_search, memory_list
from .core.export import export_render, export_bibliography
from .core.session import CiteIndexSession, SessionManager
from .utils.output import format_output


# ── Helpers ──

def _json_flag(f):
    """Add --json flag to a click command."""
    return click.option("--json", "as_json", is_flag=True, help="Output as JSON")(f)


def _resolve_json(ctx: click.Context, as_json: bool) -> bool:
    """Resolve JSON mode: command-level flag overrides global flag."""
    global_json = ctx.obj.get("global_json", False) if ctx.obj else False
    return as_json or global_json


def _output(data: Any, as_json: bool = False, ctx: Optional[click.Context] = None) -> None:
    """Print output in human or JSON format.
    
    If ctx is provided, checks both command-level as_json and global --json flag.
    """
    effective_json = as_json
    if ctx is not None and ctx.obj:
        effective_json = as_json or ctx.obj.get("global_json", False)
    click.echo(format_output(data, json_mode=effective_json))


def _get_session_mgr(ctx: click.Context) -> SessionManager:
    return ctx.obj.get("session_manager", SessionManager())


def _get_session(ctx: click.Context) -> Optional[CiteIndexSession]:
    return ctx.obj.get("current_session")


def _set_session(ctx: click.Context, session: CiteIndexSession) -> None:
    ctx.obj["current_session"] = session


# ── Root group ──

@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="cli-anything-citeindex")
@click.option("--corpus-root", default="corpus", help="Corpus root directory")
@click.option("--json", "global_json", is_flag=True, help="Default JSON output for all commands")
@click.pass_context
def cli(ctx: click.Context, corpus_root: str, global_json: bool) -> None:
    """cli-anything-citeindex — Stateful CLI for CiteIndex research infrastructure."""
    ctx.ensure_object(dict)
    ctx.obj["corpus_root"] = corpus_root
    ctx.obj["session_manager"] = SessionManager()
    ctx.obj["global_json"] = global_json
    ctx.obj["current_session"] = None

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ── Project commands ──

@cli.group()
def project() -> None:
    """Corpus management (new, info, validate, list)."""
    pass


@project.command("new")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_new_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """Create a new corpus directory structure."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_new(corpus_root=root)
    _output(result, as_json, ctx)


@project.command("info")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_info_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """Show corpus information."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_info(corpus_root=root)
    _output(result, as_json, ctx)


@project.command("validate")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_validate_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """Validate corpus structure."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_validate(corpus_root=root)
    _output(result, as_json, ctx)


@project.command("list")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def project_list_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """List documents in the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = project_list(corpus_root=root)
    _output(result, as_json, ctx)


# ── Ingest commands ──

@cli.group()
def ingest() -> None:
    """Ingest documents (file, url, crawl)."""
    pass


@ingest.command("file")
@click.argument("input_path")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model for citation extraction")
@click.option("--text-direction", "-td", type=click.Choice(["horizontal", "auto", "vertical"]), default="horizontal")
@click.option("--vertical-lang", type=click.Choice(["ch", "japan"]), default="ch")
@click.option("--lang", "-l", default="auto", help="OCR language")
@click.option("--page-range", "-p", default="1-5, -3", help="Page range")
@click.option("--type", "-t", "doc_type", type=click.Choice(["book", "thesis", "journal", "bookchapter"]), default=None)
@click.option("--no-layout", is_flag=True, help="Disable layout analysis")
@click.option("--is-primary", is_flag=True, help="Mark as primary source")
@click.option("--use-pageindex", is_flag=True, help="Use PageIndex tree building")
@click.option("--pageindex-model", default="ollama/qwen3.5:cloud")
@_json_flag
@click.pass_context
def ingest_file_cmd(ctx: click.Context, input_path: str, corpus_root: Optional[str],
                    llm: str, text_direction: str, vertical_lang: str,
                    lang: str, page_range: str, doc_type: Optional[str],
                    no_layout: bool, is_primary: bool, use_pageindex: bool,
                    pageindex_model: str, as_json: bool) -> None:
    """Ingest a file (PDF, DJVU, DOCX, etc.) into the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = ingest_file(
        input_path=input_path,
        corpus_root=root,
        llm_model=llm,
        text_direction=text_direction,
        vertical_lang=vertical_lang,
        lang=lang,
        page_range=page_range,
        doc_type=doc_type,
        use_layout=not no_layout,
        is_primary=is_primary,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
    )
    _output(result, as_json, ctx)


@ingest.command("url")
@click.argument("url")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model")
@click.option("--lang", "-l", default="auto", help="OCR language")
@click.option("--type", "-t", "doc_type", type=click.Choice(["book", "thesis", "journal", "bookchapter"]), default=None)
@click.option("--use-pageindex", is_flag=True)
@click.option("--pageindex-model", default="ollama/qwen3.5:cloud")
@_json_flag
@click.pass_context
def ingest_url_cmd(ctx: click.Context, url: str, corpus_root: Optional[str],
                   llm: str, lang: str, doc_type: Optional[str],
                   use_pageindex: bool, pageindex_model: str, as_json: bool) -> None:
    """Ingest a URL into the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = ingest_url(
        url=url,
        corpus_root=root,
        llm_model=llm,
        lang=lang,
        doc_type=doc_type,
        use_pageindex=use_pageindex,
        pageindex_model=pageindex_model,
    )
    _output(result, as_json, ctx)


@ingest.command("crawl")
@click.argument("root_url")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model")
@click.option("--update", is_flag=True, help="Re-ingest only changed pages")
@click.option("--depth", type=int, default=2, help="Max crawl depth")
@click.option("--max-pages", type=int, default=100, help="Max pages to visit")
@_json_flag
@click.pass_context
def ingest_crawl_cmd(ctx: click.Context, root_url: str, corpus_root: Optional[str],
                     llm: str, update: bool, depth: int, max_pages: int, as_json: bool) -> None:
    """Crawl and ingest all article pages from a URL."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = ingest_crawl(
        root_url=root_url,
        corpus_root=root,
        llm_model=llm,
        update=update,
        max_depth=depth,
        max_pages=max_pages,
    )
    _output(result, as_json, ctx)


# ── Search commands ──

@cli.group()
def search() -> None:
    """Search corpus (query)."""
    pass


@search.command("query")
@click.argument("query_str")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--top-k", type=int, default=20, help="Number of results")
@click.option("--cite-style", default="chicago-author-date", help="Citation style")
@click.option("--retrieval", type=click.Choice(["bm25", "pageindex", "auto"]), default="auto")
@click.option("--pageindex-model", default="ollama/qwen3.5:cloud")
@_json_flag
@click.pass_context
def search_query_cmd(ctx: click.Context, query_str: str, corpus_root: Optional[str],
                     top_k: int, cite_style: str, retrieval: str,
                     pageindex_model: str, as_json: bool) -> None:
    """Search the corpus using BM25 or PageIndex retrieval."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = search_query(
        query=query_str,
        corpus_root=root,
        top_k=top_k,
        cite_style=cite_style,
        retrieval=retrieval,
        pageindex_model=pageindex_model,
    )
    _output(result, as_json, ctx)


# ── Chat commands ──

@cli.group()
def chat() -> None:
    """Chat with trace-bound citations (ask, interactive)."""
    pass


@chat.command("ask")
@click.argument("prompt")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model for generation")
@click.option("--thread", default="default", help="Chat thread ID")
@_json_flag
@click.pass_context
def chat_ask_cmd(ctx: click.Context, prompt: str, corpus_root: Optional[str],
                 llm: str, thread: str, as_json: bool) -> None:
    """Single-shot chat with trace-bound citations."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = chat_ask(
        prompt=prompt,
        corpus_root=root,
        llm_model=llm,
        thread_id=thread,
    )
    if _resolve_json(ctx, as_json):
        _output(result, True, ctx)
    else:
        if result.get("answer_human"):
            click.echo(result["answer_human"])
        else:
            _output(result, as_json, ctx)


@chat.command("interactive")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--llm", default="ollama/qwen3", help="LLM model for generation")
@click.option("--thread", default="default", help="Chat thread ID")
@click.pass_context
def chat_interactive_cmd(ctx: click.Context, corpus_root: Optional[str],
                         llm: str, thread: str) -> None:
    """Interactive chat session with trace-bound citations."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    click.echo("CiteIndex Chat (type /quit to exit)")
    click.echo("---")
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo()
            break
        if not user_input or user_input in ("/quit", "/exit", "/q"):
            break
        result = chat_ask(prompt=user_input, corpus_root=root, llm_model=llm, thread_id=thread)
        if result.get("status") == "needs_clarification":
            click.echo("Clarification needed:")
            for q in result.get("questions", []):
                click.echo(f"  - {q}")
        elif result.get("answer_human"):
            click.echo(result["answer_human"])
        else:
            click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        click.echo()


# ── Memory commands ──

@cli.group()
def memory() -> None:
    """Memory & history (search, list)."""
    pass


@memory.command("search")
@click.argument("query")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--thread", default=None, help="Restrict to a specific thread")
@_json_flag
@click.pass_context
def memory_search_cmd(ctx: click.Context, query: str, corpus_root: Optional[str],
                      thread: Optional[str], as_json: bool) -> None:
    """Search past chat memory."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = memory_search(query=query, corpus_root=root, thread_id=thread)
    _output(result, as_json, ctx)


@memory.command("list")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@_json_flag
@click.pass_context
def memory_list_cmd(ctx: click.Context, corpus_root: Optional[str], as_json: bool) -> None:
    """List all memory threads."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = memory_list(corpus_root=root)
    _output(result, as_json, ctx)


# ── Export commands ──

@cli.group()
def export() -> None:
    """Export & render (render, bibliography)."""
    pass


@export.command("render")
@click.argument("output_path")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--format", "-f", "fmt", default="txt", help="Output format (txt, html, pdf)")
@click.option("--cite-style", default="chicago-author-date", help="Citation style")
@click.option("--overwrite", is_flag=True, help="Allow overwriting existing file")
@_json_flag
@click.pass_context
def export_render_cmd(ctx: click.Context, output_path: str, corpus_root: Optional[str],
                      fmt: str, cite_style: str, overwrite: bool, as_json: bool) -> None:
    """Render citations from the corpus to a file."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = export_render(
        output_path=output_path,
        corpus_root=root,
        format=fmt,
        cite_style=cite_style,
        overwrite=overwrite,
    )
    _output(result, as_json, ctx)


@export.command("bibliography")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.option("--cite-style", default="chicago-author-date", help="Citation style")
@_json_flag
@click.pass_context
def export_bibliography_cmd(ctx: click.Context, corpus_root: Optional[str],
                            cite_style: str, as_json: bool) -> None:
    """Export a formatted bibliography from the corpus."""
    root = corpus_root or ctx.obj.get("corpus_root", "corpus")
    result = export_bibliography(corpus_root=root, cite_style=cite_style)
    _output(result, as_json, ctx)


# ── Session commands ──

@cli.group()
def session() -> None:
    """Session management (save, load, undo, redo, status)."""
    pass


@session.command("create")
@click.option("--id", "session_id", help="Custom session ID")
@_json_flag
@click.pass_context
def session_create_cmd(ctx: click.Context, session_id: Optional[str], as_json: bool) -> None:
    """Create a new session."""
    mgr = _get_session_mgr(ctx)
    sess = mgr.create_session(session_id)
    _set_session(ctx, sess)
    _output(sess.to_dict(), as_json, ctx)


@session.command("list")
@click.option("--active-only", is_flag=True, help="Show only active sessions")
@_json_flag
@click.pass_context
def session_list_cmd(ctx: click.Context, active_only: bool, as_json: bool) -> None:
    """List saved sessions."""
    mgr = _get_session_mgr(ctx)
    sessions = mgr.list_sessions(include_inactive=not active_only)
    if as_json:
        _output([s.to_dict() for s in sessions], as_json, ctx)
    else:
        if not sessions:
            click.echo("No sessions found.")
        for s in sessions:
            click.echo(f"{s.session_id} | {s.status} | undo={s.undo_depth()} | docs={len(s.loaded_documents)} | {s.modified_at}")


@session.command("save")
@_json_flag
@click.pass_context
def session_save_cmd(ctx: click.Context, as_json: bool) -> None:
    """Save the current session."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "error", "message": "No active session. Use 'session create' first."}, as_json, ctx)
        raise SystemExit(1)
    mgr = _get_session_mgr(ctx)
    mgr.save_session(sess)
    _output({"status": "ok", "session_id": sess.session_id, "message": "Session saved"}, as_json, ctx)


@session.command("load")
@click.argument("session_id")
@_json_flag
@click.pass_context
def session_load_cmd(ctx: click.Context, session_id: str, as_json: bool) -> None:
    """Load a saved session."""
    mgr = _get_session_mgr(ctx)
    sess = mgr.load_session(session_id)
    if sess is None:
        _output({"status": "error", "message": f"Session not found: {session_id}"}, as_json, ctx)
        raise SystemExit(1)
    _set_session(ctx, sess)
    _output(sess.to_dict(), as_json, ctx)


@session.command("undo")
@_json_flag
@click.pass_context
def session_undo_cmd(ctx: click.Context, as_json: bool) -> None:
    """Undo the last action."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "error", "message": "No active session"}, as_json, ctx)
        raise SystemExit(1)
    item = sess.pop_undo()
    if item is None:
        _output({"status": "ok", "message": "Nothing to undo"}, as_json, ctx)
    else:
        mgr = _get_session_mgr(ctx)
        mgr.save_session(sess)
        _output({"status": "ok", "message": "Undone", "command": item.get("command", "?")}, as_json, ctx)


@session.command("redo")
@_json_flag
@click.pass_context
def session_redo_cmd(ctx: click.Context, as_json: bool) -> None:
    """Redo the last undone action."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "error", "message": "No active session"}, as_json, ctx)
        raise SystemExit(1)
    item = sess.pop_redo()
    if item is None:
        _output({"status": "ok", "message": "Nothing to redo"}, as_json, ctx)
    else:
        mgr = _get_session_mgr(ctx)
        mgr.save_session(sess)
        _output({"status": "ok", "message": "Redone", "command": item.get("command", "?")}, as_json, ctx)


@session.command("status")
@_json_flag
@click.pass_context
def session_status_cmd(ctx: click.Context, as_json: bool) -> None:
    """Show current session status."""
    sess = _get_session(ctx)
    if sess is None:
        _output({"status": "no_session", "message": "No active session"}, as_json, ctx)
        return
    _output({
        "status": "ok",
        "session_id": sess.session_id,
        "corpus_root": sess.corpus_root or "(not set)",
        "thread_id": sess.thread_id,
        "documents": len(sess.loaded_documents),
        "undo_depth": sess.undo_depth(),
        "redo_depth": sess.redo_depth(),
    }, as_json, ctx)


# ── REPL command ──

@cli.command("repl")
@click.option("--corpus-root", "-c", default=None, help="Corpus root directory")
@click.pass_context
def repl(ctx: click.Context, corpus_root: Optional[str]) -> None:
    """Interactive REPL mode with prompt_toolkit."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.completion import WordCompleter
    except ImportError:
        click.echo("prompt-toolkit not installed. Install with: pip install prompt-toolkit")
        raise SystemExit(1)

    root = corpus_root or ctx.obj.get("corpus_root", "corpus")

    # Banner
    click.echo("╭─────────────────────────────────────────────────────╮")
    click.echo(f"│  ◆ CiteIndex CLI v{__version__:<33} │")
    click.echo(f"│  ◇ Corpus: {root:<41} │")

    # Check for SKILL.md
    skill_path = os.path.join(os.path.dirname(__file__), "skills", "SKILL.md")
    if os.path.isfile(skill_path):
        click.echo(f"│  ◇ Skill: {skill_path:<41} │")

    click.echo("╰─────────────────────────────────────────────────────╯")

    # Completer with all commands
    commands = [
        "project new", "project info", "project validate", "project list",
        "ingest file", "ingest url", "ingest crawl",
        "search query",
        "chat ask", "chat interactive",
        "memory search", "memory list",
        "export render", "export bibliography",
        "session create", "session list", "session save", "session load",
        "session undo", "session redo", "session status",
        "help", "quit",
    ]
    completer = WordCompleter(commands, ignore_case=True)

    # Prompt session with history
    history_file = os.path.expanduser("~/.citeindex_cli_history")
    pt_session = PromptSession(
        history=FileHistory(history_file),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
    )

    click.echo()
    click.echo("Type 'help' for commands, 'quit' to exit.")
    click.echo()

    while True:
        try:
            # Build prompt with context
            info = project_info(corpus_root=root)
            doc_count = info.get("document_count", 0)
            prompt_str = f"citeindex ({doc_count} docs)> "
            user_input = pt_session.prompt(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            click.echo()
            break

        if not user_input:
            continue
        if user_input in ("quit", "exit", "q"):
            break
        if user_input == "help":
            click.echo()
            click.echo("  project   — Corpus management (new, info, validate, list)")
            click.echo("  ingest    — Ingest documents (file, url, crawl)")
            click.echo("  search    — Search corpus (query)")
            click.echo("  chat      — Chat with citations (ask, interactive)")
            click.echo("  memory    — Memory & history (search, list)")
            click.echo("  export    — Export & render (render, bibliography)")
            click.echo("  session   — Session management (save, load, undo, redo, status)")
            click.echo("  help      — Show this help")
            click.echo("  quit      — Exit REPL")
            click.echo()
            continue

        # Dispatch command through Click
        try:
            args = user_input.split()
            cli.main(args, standalone_mode=False, parent=ctx)
        except SystemExit:
            pass
        except click.exceptions.UsageError as e:
            click.echo(f"Error: {e}")
        click.echo()

    click.echo("Goodbye!")


# ── Entry point ──

def main() -> None:
    """Main entry point for cli-anything-citeindex."""
    cli()


if __name__ == "__main__":
    main()