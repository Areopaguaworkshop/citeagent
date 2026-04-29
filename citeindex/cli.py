import argparse
import json
import logging
import sys


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def _run_ingest(args: argparse.Namespace) -> int:
    from citeindex.ingestion import CiteIndexIngestionOrchestrator
    from citeindex.ingestion.models import IngestionConfig

    config = IngestionConfig(
        llm_model=args.llm,
        text_direction=args.text_direction,
        vertical_lang=args.vertical_lang,
        lang=args.lang,
        page_range=args.page_range,
        doc_type_override=args.type,
        use_layout_analysis=not args.no_layout,
        is_primary=args.is_primary,
        use_pageindex=args.use_pageindex,
        pageindex_model=args.pageindex_model,
    )
    orchestrator = CiteIndexIngestionOrchestrator(
        corpus_root=args.corpus_root,
        schema_version=args.schema_version,
    )

    if args.all_url_article or args.update_url_article:
        output = orchestrator.ingest_all_urls(
            root_url=args.input,
            config=config,
            update=args.update_url_article,
            max_depth=args.crawl_depth,
            max_pages=args.crawl_max_pages,
        )
    else:
        output = orchestrator.ingest(args.input, config=config)

    print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
    return 1 if output.get("status") == "blocked" else 0


def _run_search(args: argparse.Namespace) -> int:
    from citeindex.agents.chat import SearchPipeline

    pipeline = SearchPipeline(
        corpus_root=args.corpus_root,
    )
    result = pipeline.search(
        args.query,
        top_k=args.top_k,
        cite_style=args.cite_style,
        retrieval=args.retrieval,
        pageindex_model=args.pageindex_model,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 1


def _run_chat(args: argparse.Namespace) -> int:
    from citeindex.agents.chat import ChatPipeline

    pipeline = ChatPipeline(
        corpus_root=args.corpus_root,
        llm_model=args.llm,
    )

    if args.prompt:
        # Single-shot mode
        result = pipeline.chat(args.prompt, thread_id=args.thread)
        if result.get("answer_human"):
            print(result["answer_human"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("status") == "ok" else 1

    # Interactive loop
    print("CiteIndex Chat (type /quit to exit)")
    print("---")
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input or user_input in ("/quit", "/exit", "/q"):
            break
        result = pipeline.chat(user_input, thread_id=args.thread)
        if result.get("status") == "needs_clarification":
            print("Clarification needed:")
            for q in result.get("questions", []):
                print(f"  - {q}")
        elif result.get("answer_human"):
            print(result["answer_human"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        print()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="citeindex", description="CiteIndex — AI research knowledge infrastructure"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest", help="Deterministic CiteIndex ingestion"
    )
    ingest_parser.add_argument("input", help="Input file path or URL")
    ingest_parser.add_argument(
        "--corpus-root", default="corpus", help="Corpus output root"
    )
    ingest_parser.add_argument(
        "--schema-version", default="1.0.0", help="Schema version tag"
    )
    ingest_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logs"
    )
    ingest_parser.add_argument(
        "--llm",
        default="ollama/qwen3",
        help="LLM model for citation extraction (default: ollama/qwen3)",
    )
    ingest_parser.add_argument(
        "--text-direction",
        "-td",
        choices=["horizontal", "auto", "vertical"],
        default="horizontal",
        help="Text direction for PDF processing",
    )
    ingest_parser.add_argument(
        "--vertical-lang",
        choices=["ch", "japan"],
        default="ch",
        help="Primary language for vertical text OCR (default: ch)",
    )
    ingest_parser.add_argument(
        "--lang",
        "-l",
        default="auto",
        help="OCR language (default: auto-detect)",
    )
    ingest_parser.add_argument(
        "--page-range",
        "-p",
        default="1-5, -3",
        help='Page range for extraction (default: "1-5, -3")',
    )
    ingest_parser.add_argument(
        "--type",
        "-t",
        choices=["book", "thesis", "journal", "bookchapter"],
        help="Override automatic document type detection",
    )
    ingest_parser.add_argument(
        "--no-layout",
        action="store_true",
        help="Disable layout analysis (column/footnote detection)",
    )
    ingest_parser.add_argument(
        "--is-primary",
        action="store_true",
        help="Mark source as primary (line-level granularity). Default: secondary (paragraph-level)",
    )
    ingest_parser.add_argument(
        "--use-pageindex",
        action="store_true",
        help="Use PageIndex LLM-driven tree building for section hierarchy (requires Ollama)",
    )
    ingest_parser.add_argument(
        "--pageindex-model",
        default="ollama/qwen3.5:cloud",
        help="LLM model for PageIndex tree building (default: ollama/qwen3.5:cloud)",
    )
    ingest_parser.add_argument(
        "--citation-style",
        "-cs",
        default="chicago-author-date",
        help="Citation style for formatted output (default: chicago-author-date)",
    )
    ingest_parser.add_argument(
        "--all-url-article",
        "-aua",
        action="store_true",
        help="Crawl the input URL and ingest all discovered article pages",
    )
    ingest_parser.add_argument(
        "--update-url-article",
        "-uua",
        action="store_true",
        help="Crawl and compare content hashes; skip unchanged pages, re-ingest updated ones",
    )
    ingest_parser.add_argument(
        "--crawl-depth",
        type=int,
        default=2,
        help="Max BFS crawl depth for --all-url-article (default: 2)",
    )
    ingest_parser.add_argument(
        "--crawl-max-pages",
        type=int,
        default=100,
        help="Max pages the crawler will visit for --all-url-article (default: 100)",
    )

    search_parser = subparsers.add_parser(
        "search", help="Search over ingested corpus (BM25 or PageIndex reasoning)"
    )
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--corpus-root", default="corpus", help="Corpus root directory"
    )
    search_parser.add_argument(
        "--top-k", type=int, default=20, help="Number of results to return (default: 20)"
    )
    search_parser.add_argument(
        "--cite-style",
        default="chicago-author-date",
        help="Citation style for formatted output (default: chicago-author-date)",
    )
    search_parser.add_argument(
        "--retrieval",
        choices=["bm25", "pageindex", "auto"],
        default="auto",
        help="Retrieval method: bm25 (keyword), pageindex (LLM reasoning), auto (query planner decides). Default: auto",
    )
    search_parser.add_argument(
        "--pageindex-model",
        default="ollama/qwen3.5:cloud",
        help="LLM model for PageIndex retrieval (default: ollama/qwen3.5:cloud)",
    )
    search_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logs"
    )

    chat_parser = subparsers.add_parser(
        "chat", help="Retrieval-augmented chat with trace-bound citations"
    )
    chat_parser.add_argument("--prompt", "-p", default=None, help="Single-shot prompt (non-interactive)")
    chat_parser.add_argument("--thread", default="default", help="Chat thread id")
    chat_parser.add_argument(
        "--corpus-root", default="corpus", help="Corpus root directory"
    )
    chat_parser.add_argument(
        "--llm",
        default="ollama/qwen3",
        help="LLM model for generation (default: ollama/qwen3)",
    )
    chat_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logs"
    )

    # ── memory subcommand ──────────────────────────────────────────────
    memory_parser = subparsers.add_parser(
        "memory", help="Search past chat memory"
    )
    memory_parser.add_argument("action", choices=["search", "list"], help="Memory action")
    memory_parser.add_argument("query", nargs="?", default="", help="Search query")
    memory_parser.add_argument("--thread", default=None, help="Restrict to a specific thread")
    memory_parser.add_argument(
        "--corpus-root", default="corpus", help="Corpus root directory"
    )
    memory_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logs"
    )

    # ── plugin subcommand ─────────────────────────────────────────────
    plugin_parser = subparsers.add_parser(
        "plugin", help="Manage CiteIndex plugins"
    )
    plugin_parser.add_argument(
        "action", choices=["install", "list"],
        help="Plugin action",
    )
    plugin_parser.add_argument(
        "path", nargs="?", default=None,
        help="Plugin path or git URL (for install)",
    )
    plugin_parser.add_argument(
        "--plugins-dir", default="plugins", help="Plugins directory"
    )
    plugin_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose logs"
    )

    return parser


def _run_memory(args: argparse.Namespace) -> int:
    from citeindex.agents.memory import MemoryStore

    store = MemoryStore(memory_dir=f"{args.corpus_root}/.memory")

    if args.action == "list":
        threads = store._list_threads()
        if not threads:
            print(json.dumps({"status": "ok", "threads": []}, indent=2))
        else:
            print(json.dumps({"status": "ok", "threads": threads}, indent=2))
        return 0

    if args.action == "search":
        if not args.query:
            print(json.dumps({"status": "error", "message": "Query required for search"}, indent=2))
            return 1
        results = store.search(args.query, thread_id=args.thread)
        output = {
            "status": "ok",
            "query": args.query,
            "total": len(results),
            "results": [e.to_dict() for e in results[:20]],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    return 0


def _run_plugin(args: argparse.Namespace) -> int:
    import os

    plugins_dir = os.path.abspath(args.plugins_dir)

    if args.action == "list":
        plugins = []
        if os.path.isdir(plugins_dir):
            for name in sorted(os.listdir(plugins_dir)):
                plugin_dir = os.path.join(plugins_dir, name)
                manifest_path = os.path.join(plugin_dir, "plugin.toml")
                if os.path.isfile(manifest_path):
                    try:
                        import tomllib
                    except ImportError:
                        try:
                            import tomli as tomllib
                        except ImportError:
                            plugins.append({"name": name, "status": "manifest unreadable (no toml parser)"})
                            continue
                    with open(manifest_path, "rb") as f:
                        manifest = tomllib.load(f)
                    plugins.append({
                        "name": manifest.get("name", name),
                        "version": manifest.get("version", "?"),
                        "commands": list(manifest.get("commands", {}).keys()),
                    })
        print(json.dumps({"status": "ok", "plugins": plugins}, indent=2))
        return 0

    if args.action == "install":
        if not args.path:
            print(json.dumps({"status": "error", "message": "Path or URL required for install"}, indent=2))
            return 1
        # Simple local copy for now (Rust plugin manager handles git)
        import shutil

        src = os.path.abspath(args.path)
        if not os.path.isdir(src):
            print(json.dumps({"status": "error", "message": f"Source not found: {src}"}, indent=2))
            return 1

        # Read manifest to get name
        manifest_path = os.path.join(src, "plugin.toml")
        if not os.path.isfile(manifest_path):
            print(json.dumps({"status": "error", "message": "No plugin.toml found"}, indent=2))
            return 1

        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                print(json.dumps({"status": "error", "message": "No toml parser available"}, indent=2))
                return 1

        with open(manifest_path, "rb") as f:
            manifest = tomllib.load(f)

        name = manifest.get("name", os.path.basename(src))
        dest = os.path.join(plugins_dir, name)
        os.makedirs(plugins_dir, exist_ok=True)

        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

        print(json.dumps({
            "status": "ok",
            "message": f"Plugin '{name}' installed",
            "path": dest,
        }, indent=2))
        return 0

    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(getattr(args, "verbose", False))

    if args.command == "ingest":
        code = _run_ingest(args)
    elif args.command == "search":
        code = _run_search(args)
    elif args.command == "chat":
        code = _run_chat(args)
    elif args.command == "memory":
        code = _run_memory(args)
    elif args.command == "plugin":
        code = _run_plugin(args)
    else:
        code = _run_chat(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
