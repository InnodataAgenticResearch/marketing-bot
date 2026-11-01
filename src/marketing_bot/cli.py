"""
Command-line interface (`marketing-bot`) for Innodata PR & Market Intelligence.

Supports:
- `upstream-status`
- `strategy-summary`
- `mcp-search`
- `generate-daily --date YYYY-MM-DD [--seed-file path] [--live]`
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from marketing_bot.agility_mcp import (
    AgilityMcpClient,
    HttpTransport,
    MediaMention,
    deduplicate_mentions,
    evaluate_mention_positioning,
)
from marketing_bot.roundup import (
    default_seed_mentions,
    generate_daily_roundup,
    load_mentions_from_seed_file,
)
from marketing_bot.strategy import (
    MarketingStrategy,
    default_repo_root,
    default_strategy_path,
    default_upstream_pin_path,
    format_strategy_summary,
    load_marketing_strategy,
    load_upstream_artbot_pin,
)


def harvest_live_mentions(
    client: AgilityMcpClient,
    strategy: MarketingStrategy,
    *,
    date_range: str = "LAST_7_DAYS",
    page_size: int = 10,
) -> list[MediaMention]:
    """
    Harvest mentions across Agility PR MCP (`ad_hoc_search`) and configured saved topics.
    """
    collected: list[MediaMention] = []
    mcp_query = (
        '("Innodata" OR "Agent Reliability" OR "Pilot Purgatory" OR "Scale AI" OR "Palantir") '
        'AND ("AI" OR "enterprise")'
    )
    collected.extend(
        client.call_ad_hoc_search(
            mcp_query,
            date_range=date_range,
            page_size=page_size,
            topic_name="MCP Strategic Pulse",
        )
    )
    for topic in strategy.agility_topics:
        collected.extend(
            client.search_saved_topic(
                topic.topic_id,
                date_range=date_range,
                page_size=page_size,
                topic_name=topic.name,
            )
        )
    return collected


def build_parser() -> argparse.ArgumentParser:
    """Construct the `marketing-bot` CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="marketing-bot",
        description="Marketing-Bot: Innodata PR & Market Intelligence Agent CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    up_parser = subparsers.add_parser(
        "upstream-status",
        help="Verify upstream ArtBOT release tag and public API contract lock",
    )
    up_parser.add_argument("--json", action="store_true", help="Output raw JSON pin data")

    subparsers.add_parser(
        "strategy-summary",
        help="Print Innodata's 6-pillar taxonomy, 5 accelerators, and competitive matrix",
    )

    search_parser = subparsers.add_parser(
        "mcp-search",
        help="Run an ad-hoc Expert Search query via Agility PR MCP and score mentions",
    )
    search_parser.add_argument("query", help="Agility PR Expert Search boolean query")
    search_parser.add_argument(
        "--date-range",
        default="LAST_7_DAYS",
        help="Relative date range (default: LAST_7_DAYS)",
    )
    search_parser.add_argument(
        "--page-size",
        type=int,
        default=10,
        help="Number of results to fetch (default: 10)",
    )
    search_parser.add_argument(
        "--api-key",
        default=None,
        help="Agility PR API key (defaults to AGILITYPR_API_KEY env var)",
    )

    daily_parser = subparsers.add_parser(
        "generate-daily",
        help="Generate daily intelligence roundup and category briefs",
    )
    daily_parser.add_argument(
        "--date",
        default="2026-11-01",
        help="Target roundup date in YYYY-MM-DD format",
    )
    daily_parser.add_argument(
        "--seed-file",
        default=None,
        help="Optional JSON seed file containing mentions",
    )
    daily_parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch live mentions from Agility PR MCP and saved topics",
    )
    daily_parser.add_argument(
        "--api-key",
        default=None,
        help="Agility PR API key for --live mode (defaults to AGILITYPR_API_KEY env var)",
    )

    return parser


def main(
    argv: list[str] | None = None,
    *,
    repo_root: Path | None = None,
    transport: HttpTransport | None = None,
    env: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Command-line entrypoint for `marketing-bot`."""
    out_stream = sys.stdout if stdout is None else stdout
    err_stream = sys.stderr if stderr is None else stderr
    active_env: Mapping[str, str] = os.environ if env is None else env
    root = default_repo_root() if repo_root is None else repo_root

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "upstream-status":
        pin = load_upstream_artbot_pin(default_upstream_pin_path(root))
        if args.json:
            print(json.dumps(pin, indent=2), file=out_stream)
        else:
            allowlist = pin["public_api_allowlist"]
            print(
                f"Upstream Repo:   {pin['upstream_repo']}\n"
                f"Upstream Tag:    {pin['upstream_tag']}\n"
                f"Upstream Commit: {pin['upstream_commit']}\n"
                f"Allowed Symbols: {len(allowlist)}",
                file=out_stream,
            )
        return 0

    strategy = load_marketing_strategy(default_strategy_path(root))

    if args.command == "strategy-summary":
        print(format_strategy_summary(strategy), file=out_stream)
        return 0

    if args.command == "mcp-search":
        api_key = str(args.api_key or active_env.get("AGILITYPR_API_KEY") or "").strip()
        if not api_key:
            print(
                "Error: AGILITYPR_API_KEY is required for mcp-search (pass --api-key or set env)",
                file=err_stream,
            )
            return 1
        client = AgilityMcpClient(api_key, transport=transport)
        raw_mentions = client.call_ad_hoc_search(
            str(args.query),
            date_range=str(args.date_range),
            page_size=int(args.page_size),
        )
        deduped = deduplicate_mentions(raw_mentions)
        evaluated = [evaluate_mention_positioning(m, strategy) for m in deduped]
        payload: list[dict[str, Any]] = [
            {
                "title": item.mention.title,
                "url": item.mention.url,
                "outlet": item.mention.outlet,
                "published_date": item.mention.published_date,
                "category": item.category,
                "relevance_score": item.relevance_score,
                "matched_pillars": list(item.matched_pillars),
                "matched_accelerators": list(item.matched_accelerators),
                "matched_competitors": list(item.matched_competitors),
                "why_it_matters": item.why_it_matters,
                "positioning_angle": item.positioning_angle,
                "recommended_action": item.recommended_action,
            }
            for item in evaluated
        ]
        print(json.dumps({"count": len(payload), "results": payload}, indent=2), file=out_stream)
        return 0

    # args.command == "generate-daily"
    date_str = str(args.date).strip()
    if args.seed_file:
        mentions = load_mentions_from_seed_file(Path(str(args.seed_file)))
    elif args.live:
        api_key = str(args.api_key or active_env.get("AGILITYPR_API_KEY") or "").strip()
        if not api_key:
            print(
                "Error: AGILITYPR_API_KEY is required for --live roundup generation",
                file=err_stream,
            )
            return 1
        client = AgilityMcpClient(api_key, transport=transport)
        mentions = harvest_live_mentions(client, strategy)
    else:
        mentions = default_seed_mentions(date_str)

    paths = generate_daily_roundup(
        repo_root=root,
        date_str=date_str,
        mentions=mentions,
        strategy=strategy,
    )
    print(
        f"Generated daily intelligence roundup for {paths.date_str}:\n"
        f"  - {paths.roundup_file}\n"
        f"  - {paths.brand_file}\n"
        f"  - {paths.competitive_file}\n"
        f"  - {paths.trends_file}\n"
        f"  - {paths.readme_file}",
        file=out_stream,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    sys.exit(main())
