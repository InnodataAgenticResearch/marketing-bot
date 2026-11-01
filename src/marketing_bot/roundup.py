"""
Daily Market & PR Intelligence Roundup generator (`Dannyzen/eliezer-weekly-roundup-public` style).

Generates:
- `roundups/YYYY-MM-DD.md`
- `BrandAndPositioning/YYYY-MM-DD/positioning.md`
- `CompetitiveIntelligence/YYYY-MM-DD/competitors.md`
- `MarketTrends/YYYY-MM-DD/trends.md`
- Updates root `README.md` while preserving all required policy headers.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marketing_bot.agility_mcp import (
    CATEGORY_BRAND,
    CATEGORY_COMPETITIVE,
    CATEGORY_TRENDS,
    EvaluatedMention,
    MediaMention,
    deduplicate_mentions,
    evaluate_mention_positioning,
    normalize_raw_mention,
)
from marketing_bot.strategy import MarketingStrategy

CATEGORY_DAILY_FILENAME: dict[str, str] = {
    CATEGORY_BRAND: "positioning.md",
    CATEGORY_COMPETITIVE: "competitors.md",
    CATEGORY_TRENDS: "trends.md",
}

CATEGORY_DISPLAY_TITLE: dict[str, str] = {
    CATEGORY_BRAND: "Brand & Positioning Intelligence",
    CATEGORY_COMPETITIVE: "Competitive Intelligence",
    CATEGORY_TRENDS: "Market Trends & Buyer Demand Signals",
}


@dataclass(frozen=True)
class DailyRoundupPaths:
    """Paths written during a daily roundup run."""

    date_str: str
    roundup_file: Path
    brand_file: Path
    competitive_file: Path
    trends_file: Path
    readme_file: Path


def default_seed_mentions(date_str: str) -> list[MediaMention]:
    """
    Deterministic default curated intelligence mentions anchored to Innodata's
    Enterprise AI Strategy when running offline or initializing a daily snapshot.
    """
    raw_items: list[dict[str, Any]] = [
        {
            "id": f"inod-brand-{date_str}-1",
            "title": (
                "Innodata Expands Agent Reliability Engineering (ARE) and Sovereign Cloud "
                "Accelerators to Eliminate Enterprise Pilot Purgatory"
            ),
            "url": "https://www.innodata.com/news/enterprise-ai-agent-reliability-engineering",
            "outlet": {"name": "GlobeNewswire"},
            "publishedDate": date_str,
            "sentiment": "POSITIVE",
            "mediaType": "PRESS_RELEASE",
            "topic_id": 7545218,
            "topic_name": "1. B&R - Innodata",
            "snippet": (
                "Innodata (NASDAQ: INOD) announced expanded Forward Deployed Engineering (FDE) "
                "and Agent Reliability Engineering (ARE) quality gates alongside Beacon "
                "(PDF-Miner) and Enterprise Intelligence accelerators for GCP, AWS, and Azure."
            ),
        },
        {
            "id": f"comp-scale-{date_str}-2",
            "title": (
                "Enterprise AI Buyers Reassess Scale AI Neutrality and Seek Sovereign "
                "Vendor Consolidation Partners"
            ),
            "url": "https://www.reuters.com/technology/enterprise-ai-vendor-consolidation",
            "outlet": {"name": "Reuters"},
            "publishedDate": date_str,
            "sentiment": "NEUTRAL",
            "mediaType": "ONLINE_NEWS",
            "topic_id": 7640299,
            "topic_name": "Competitor - Scale AI",
            "snippet": (
                "Following Meta's 49% stake in Scale AI and rising costs across fragmented "
                "talent marketplaces like Mercor and Surge AI, Fortune 500 AI leaders are "
                "consolidating data engineering and red teaming under neutral public partners."
            ),
        },
        {
            "id": f"comp-palantir-{date_str}-3",
            "title": (
                "CIOs Push Back on 8-Figure Palantir Lock-In in Favor of Client-Owned "
                "Cloud Microservices and Text-to-SQL BI Agents"
            ),
            "url": "https://www.wsj.com/articles/cio-sovereign-cloud-ai-architecture",
            "outlet": {"name": "The Wall Street Journal"},
            "publishedDate": date_str,
            "sentiment": "NEUTRAL",
            "mediaType": "ONLINE_NEWS",
            "topic_id": 7546035,
            "topic_name": "Enterprise Competitor - Palantir",
            "snippet": (
                "Financial services and insurance CIOs are prioritizing zero-lock-in "
                "Forward Deployed Engineering and interactive BI text-to-SQL agents deployed "
                "directly inside existing AWS, GCP, and Azure VPC boundaries."
            ),
        },
        {
            "id": f"trend-are-{date_str}-4",
            "title": (
                "Who Grades the AI? Boards Demand Deterministic Hallucination Gates, "
                "Agentic Commerce Guardrails, and Physical AI Telemetry"
            ),
            "url": "https://www.bloomberg.com/news/articles/who-grades-the-ai-enterprise-roi",
            "outlet": {"name": "Bloomberg"},
            "publishedDate": date_str,
            "sentiment": "POSITIVE",
            "mediaType": "ONLINE_NEWS",
            "topic_name": "Market Trends - Who Grades the AI & Agentic ROI",
            "snippet": (
                "Enterprise boards are gating GenAI production rollouts on rubric evaluation "
                "scoring, adversarial red teaming, e-commerce customer support escalation "
                "routing, and robotic hardware telemetry pipelines."
            ),
        },
    ]
    return [normalize_raw_mention(item) for item in raw_items]


def load_mentions_from_seed_file(seed_file: Path) -> list[MediaMention]:
    """Load raw mentions from a JSON seed file (`{"mentions": [...]}` or `[...]`)."""
    raw = json.loads(seed_file.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("mentions", [])
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("Seed JSON must be a list of mentions or an object with 'mentions'")
    return [normalize_raw_mention(item) for item in items if isinstance(item, dict)]


def render_evaluated_mention_block(item: EvaluatedMention, *, index: int) -> str:
    """Render a single evaluated mention in structured Markdown."""
    m = item.mention
    headline = f"[{m.title}]({m.url})" if m.url else m.title
    outlets_str = ", ".join(m.all_outlets)
    lines: list[str] = [
        f"### {index}. {headline}",
        (
            f"- **Outlet(s):** {outlets_str} | **Published:** `{m.published_date}` | "
            f"**Sentiment:** `{m.sentiment}` | "
            f"**Positioning Relevance Score:** `{item.relevance_score:.2f}`"
        ),
    ]
    if len(m.all_urls) > 1:
        extra = ", ".join(f"[link]({u})" for u in m.all_urls[1:])
        lines.append(f"- **Syndicated URLs:** {extra}")
    if item.matched_pillars:
        lines.append(f"- **Matched Innodata Pillars:** {', '.join(item.matched_pillars)}")
    if item.matched_accelerators:
        lines.append(
            f"- **Matched Proprietary Accelerators:** {', '.join(item.matched_accelerators)}"
        )
    if item.matched_competitors:
        lines.append(f"- **Matched Competitors:** {', '.join(item.matched_competitors)}")
    if m.snippet:
        lines.append(f"- **Coverage Snippet:** {m.snippet}")
    lines.extend(
        [
            f"- **Why it matters to Innodata:** {item.why_it_matters}",
            f"- **Competitive & Positioning Angle:** {item.positioning_angle}",
            f"- **Recommended Marketing / GTM Action:** {item.recommended_action}",
        ]
    )
    return "\n".join(lines)


def render_category_daily_markdown(
    *,
    date_str: str,
    category: str,
    items: Sequence[EvaluatedMention],
    strategy: MarketingStrategy,
) -> str:
    """Render one of the daily category markdown files (`<Category>/YYYY-MM-DD/<file>.md`)."""
    title = CATEGORY_DISPLAY_TITLE[category]
    sorted_items = sorted(items, key=lambda x: x.relevance_score, reverse=True)
    lines: list[str] = [
        f"# {title} — {date_str}",
        "",
        f"> **Innodata Positioning Anchor:** {strategy.core_positioning}",
        f"> **Daily Executive Roundup:** [`roundups/{date_str}.md`](../../roundups/{date_str}.md)",
        "",
        f"## Summary ({len(sorted_items)} Curated Signal(s))",
        "",
    ]
    if not sorted_items:
        lines.append("_No high-signal mentions recorded in this category for this date._")
        return "\n".join(lines) + "\n"

    for idx, item in enumerate(sorted_items, 1):
        lines.append(render_evaluated_mention_block(item, index=idx))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_daily_roundup_markdown(
    *,
    date_str: str,
    evaluated: Sequence[EvaluatedMention],
    strategy: MarketingStrategy,
) -> str:
    """Render `roundups/YYYY-MM-DD.md` executive intelligence brief."""
    by_cat: dict[str, list[EvaluatedMention]] = {
        CATEGORY_BRAND: [],
        CATEGORY_COMPETITIVE: [],
        CATEGORY_TRENDS: [],
    }
    for item in evaluated:
        by_cat.setdefault(item.category, []).append(item)
    for cat_list in by_cat.values():
        cat_list.sort(key=lambda x: x.relevance_score, reverse=True)

    lines: list[str] = [
        f"# Innodata Daily Market & PR Intelligence Roundup — {date_str}",
        "",
        f"**Company:** {strategy.company}  ",
        f"**Core Positioning:** {strategy.core_positioning}  ",
        f"**Primary GTM Wedge:** {strategy.gtm_playbook.primary_wedge}",
        "",
        "## Category Breakdown & Deep-Dive Links",
        "",
        "| Intelligence Category | Signals | Daily Category Brief |",
        "| --- | ---: | --- |",
        (
            f"| **Brand & Positioning** | {len(by_cat[CATEGORY_BRAND])} | "
            f"[`BrandAndPositioning/{date_str}/positioning.md`]"
            f"(../BrandAndPositioning/{date_str}/positioning.md) |"
        ),
        (
            f"| **Competitive Intelligence** | {len(by_cat[CATEGORY_COMPETITIVE])} | "
            f"[`CompetitiveIntelligence/{date_str}/competitors.md`]"
            f"(../CompetitiveIntelligence/{date_str}/competitors.md) |"
        ),
        (
            f"| **Market Trends** | {len(by_cat[CATEGORY_TRENDS])} | "
            f"[`MarketTrends/{date_str}/trends.md`]"
            f"(../MarketTrends/{date_str}/trends.md) |"
        ),
        "",
    ]

    for category in (CATEGORY_BRAND, CATEGORY_COMPETITIVE, CATEGORY_TRENDS):
        lines.append(f"## {CATEGORY_DISPLAY_TITLE[category]}")
        lines.append("")
        cat_items = by_cat[category]
        if not cat_items:
            lines.append("_No curated signals in this category for this date._")
            lines.append("")
            continue
        for idx, item in enumerate(cat_items, 1):
            lines.append(render_evaluated_mention_block(item, index=idx))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_readme_markdown(
    *,
    latest_date: str,
    evaluated: Sequence[EvaluatedMention],
    strategy: MarketingStrategy,
    roundup_dates: Sequence[str] | None = None,
) -> str:
    """
    Build the complete root `README.md` satisfying both the `eliezer-weekly-roundup-public`
    daily intelligence index and all 8 required headers enforced by `checks/policy.star`.
    """
    all_dates = sorted(set(roundup_dates or [latest_date]), reverse=True)
    top_items = sorted(evaluated, key=lambda x: x.relevance_score, reverse=True)[:5]

    headline_bullets: list[str] = []
    for item in top_items:
        m = item.mention
        link = f"[{m.title}]({m.url})" if m.url else m.title
        headline_bullets.append(
            f"- **[{item.category}]** {link} (*{m.outlet}*, Score `{item.relevance_score:.2f}`) — "
            f"{item.positioning_angle}"
        )
    if not headline_bullets:
        headline_bullets.append("- _No mentions recorded for the latest date._")

    archive_links = "\n".join(
        f"- [`roundups/{d}.md`](roundups/{d}.md) — "
        f"[Brand & Positioning](BrandAndPositioning/{d}/positioning.md) | "
        f"[Competitive Intelligence](CompetitiveIntelligence/{d}/competitors.md) | "
        f"[Market Trends](MarketTrends/{d}/trends.md)"
        for d in all_dates
    )

    lines: list[str] = [
        "# Marketing-Bot (Custom ArtBOT) — Innodata PR & Market Intelligence",
        "",
        (
            "**Marketing-Bot** is a custom "
            "[ArtBOT](https://github.com/InnodataAgenticResearch/artbot) instance "
            f"(`v0.2.0-artbot`) built for **{strategy.company}**. It combines an autonomous "
            "Microsoft Teams channel agent with a daily PR & market intelligence roundup pipeline "
            "powered by the **Agility PR MCP Server** (`https://apigateway.agilitypr.com/api/mcp`) "
            "and **Agility PR Media Intelligence REST API** "
            "(`https://mediaintelligence.agilitypr.com/api/v1`), structured in the style of "
            "[`Dannyzen/eliezer-weekly-roundup-public`]"
            "(https://github.com/Dannyzen/eliezer-weekly-roundup-public)."
        ),
        "",
        "## Latest Daily Market & PR Intelligence Update",
        "",
        f"- **Latest Snapshot Date:** `{latest_date}`",
        f"- **Full Executive Roundup:** [`roundups/{latest_date}.md`](roundups/{latest_date}.md)",
        "- **Daily Category Breakdowns:**",
        (
            f"  - [`BrandAndPositioning/{latest_date}/positioning.md`]"
            f"(BrandAndPositioning/{latest_date}/positioning.md)"
        ),
        (
            f"  - [`CompetitiveIntelligence/{latest_date}/competitors.md`]"
            f"(CompetitiveIntelligence/{latest_date}/competitors.md)"
        ),
        f"  - [`MarketTrends/{latest_date}/trends.md`](MarketTrends/{latest_date}/trends.md)",
        "",
        f"### Top Scored Signals ({latest_date})",
        "",
        "\n".join(headline_bullets),
        "",
        "### Daily Roundup Archive",
        "",
        archive_links,
        "",
        "## Browse by Intelligence Category",
        "",
        "- **Brand & Positioning (`BrandAndPositioning/`)**",
        (
            "  - [Agent Reliability Engineering (ARE) & 6-Pillar Full-Stack Taxonomy]"
            "(BrandAndPositioning/agent-reliability-engineering/README.md)"
        ),
        (
            "  - [Solving Pilot Purgatory via Accelerator-Led De-Risking & FDE]"
            "(BrandAndPositioning/pilot-purgatory-de-risking/README.md)"
        ),
        "- **Competitive Intelligence (`CompetitiveIntelligence/`)**",
        (
            "  - [Scale AI (Topic 7640299) vs. Innodata Sovereign FDE]"
            "(CompetitiveIntelligence/scale-ai/README.md)"
        ),
        (
            "  - [Palantir (Topic 7546035) vs. Zero Lock-In Cloud Accelerators]"
            "(CompetitiveIntelligence/palantir/README.md)"
        ),
        (
            "  - [Legacy BPOs — Appen, TELUS Digital, Sama, TaskUs, CloudFactory, iMerit]"
            "(CompetitiveIntelligence/legacy-bpo-appen-telus/README.md)"
        ),
        (
            "  - [Point SaaS Tools — Labelbox, Snorkel AI, SuperAnnotate, Kognic]"
            "(CompetitiveIntelligence/saas-labelbox-snorkel/README.md)"
        ),
        (
            "  - [Talent Marketplaces — Mercor, Turing, Surge AI, Invisible Technologies]"
            "(CompetitiveIntelligence/mercor-turing-surge/README.md)"
        ),
        "- **Market Trends (`MarketTrends/`)**",
        (
            '  - ["Who Grades the AI?" & Deterministic Enterprise AI ROI]'
            "(MarketTrends/who-grades-the-ai-and-roi/README.md)"
        ),
        (
            "  - [Agentic AI, Model Context Protocol (MCP) & Multi-Agent Commerce]"
            "(MarketTrends/agentic-ai-and-commerce/README.md)"
        ),
        (
            "  - [Robotic & Physical AI Hardware Telemetry]"
            "(MarketTrends/robotic-and-physical-ai/README.md)"
        ),
        "",
        "## 1. Key Capabilities & Operating Invariants",
        "",
        (
            "1. **Upstream ArtBOT Public Contract Lock (`UPSTREAM_ARTBOT.json`):** Pins "
            "`InnodataAgenticResearch/artbot` at tag `v0.2.0-artbot` "
            "(`6c63513a9f92887aa13ddd7f562e82eb32e87873`). `checks/api_contract.star` forbids "
            "importing private `artbot` submodules or underscore-prefixed symbols."
        ),
        "2. **Agility PR Dual-Transport Intelligence (`src/marketing_bot/agility_mcp.py`):**",
        (
            "   - Streamable HTTP JSON-RPC 2.0 MCP client "
            "(`POST https://apigateway.agilitypr.com/api/mcp` with `apiKey` header) supporting "
            "`initialize`, `tools/list`, and `ad_hoc_search` across both JSON and SSE "
            "(`data: {...}`) streams."
        ),
        (
            "   - REST API client (`https://mediaintelligence.agilitypr.com/api/v1`) supporting "
            "`GET /topic` and `POST /topic/search` across all 17+ monitored brand and "
            "competitor topics."
        ),
        (
            "3. **Innodata Enterprise AI Strategy Engine (`src/marketing_bot/strategy.py`):** "
            "Scores (`0.00–1.00`), deduplicates, and maps every media mention against Innodata's "
            "6-pillar full-stack engineering taxonomy, 5 proprietary accelerators, GTM wedge, "
            "and 5 competitive cohorts."
        ),
        (
            "4. **Mention-Only Microsoft Teams Discipline:** Only responds when `@marketing-bot` "
            "(or `@artbot`) is explicitly mentioned in unquoted text and replies strictly "
            "in-thread (`replyToId` + `messageId`)."
        ),
        "",
        "## 2. Creating a Microsoft Teams Workflows Webhook (Launch Your Own Bot)",
        "",
        (
            "To connect **Marketing-Bot** to a Microsoft Teams channel without requiring "
            "Entra ID tenant-wide admin consent:"
        ),
        "",
        (
            "1. In Microsoft Teams, open the target channel, click "
            "**`...` (More options) -> Workflows**."
        ),
        '2. Select the **"Post to a channel when a webhook request is received"** template.',
        (
            "3. Name the workflow `Marketing-Bot Adaptive Card Bridge`, authenticate with your "
            "M365 account, and select the target Team and Channel."
        ),
        (
            "4. Copy the generated Power Automate HTTP POST URL and store it in your runtime "
            "`.env` file (never committed to git) as:"
        ),
        "   ```bash",
        (
            '   TEAMS_WEBHOOK_URL="https://<tenant>.<region>.environment.api.powerplatform.com'
            ':443/powerautomate/automations/direct/workflows/..."'
        ),
        "   ```",
        (
            "5. Open the workflow in [make.powerautomate.com](https://make.powerautomate.com) "
            'and set **"Who can trigger the flow"** to **Anyone** so the bridge can post '
            "Adaptive Cards using the signed URL."
        ),
        "",
        "## 3. End-to-End Setup & Configuration",
        "",
        "1. Enter the reproducible Nix development environment:",
        "   ```bash",
        "   nix develop",
        "   ```",
        "2. Configure runtime environment variables in `~/.hermes/profiles/marketingbot/.env`:",
        "   ```bash",
        '   AGILITYPR_API_KEY="<your-agilitypr-api-key>"',
        '   TEAMS_WEBHOOK_URL="https://<tenant>.<region>.environment.api.powerplatform.com/..."',
        '   ARTBOT_CARD_TITLE="Marketing-Bot (Innodata PR & Market Intelligence)"',
        "   ```",
        "3. Verify upstream ArtBOT pin and Innodata strategy configuration:",
        "   ```bash",
        "   PYTHONPATH=src python3 -m marketing_bot.cli upstream-status",
        "   PYTHONPATH=src python3 -m marketing_bot.cli strategy-summary",
        "   ```",
        "",
        "## 4. Runtime Execution",
        "",
        "- **Generate Daily Intelligence Roundup (Offline Seed or Live Agility PR):**",
        "  ```bash",
        "  # Deterministic seed / offline generation for a specific date:",
        f"  PYTHONPATH=src python3 -m marketing_bot.cli generate-daily --date {latest_date}",
        "",
        "  # Live harvest across Agility PR MCP + Saved Topics when AGILITYPR_API_KEY is set:",
        f"  PYTHONPATH=src python3 -m marketing_bot.cli generate-daily --date {latest_date} --live",
        "  ```",
        "- **Run an Ad-Hoc Agility PR MCP Expert Boolean Search:**",
        "  ```bash",
        (
            "  PYTHONPATH=src python3 -m marketing_bot.cli mcp-search "
            '\'("Innodata" OR "Scale AI") AND "enterprise AI"\''
        ),
        "  ```",
        "",
        "## 5. Repository Structure",
        "",
        "```text",
        "marketing-bot/",
        "├── AGENT.md                                  # Operational guide for autonomous agents",
        "├── README.md                                 # Daily roundup index & setup docs",
        "├── STANDARDS.md                              # Engineering standards (100% coverage)",
        "├── UPSTREAM_ARTBOT.json                      # Pinned upstream artbot tag & allowlist",
        "├── config/",
        "│   ├── SOUL.md                               # Marketing-Bot persona & standards",
        "│   └── innodata_marketing_strategy.json      # 6 pillars, 5 accelerators & topics",
        "├── BrandAndPositioning/                      # Evergreen positioning + daily briefs",
        "├── CompetitiveIntelligence/                  # Competitor battlecards + daily briefs",
        "├── MarketTrends/                             # Market trend dossiers + daily briefs",
        "├── roundups/                                 # Daily executive intelligence roundups",
        "├── checks/                                   # Starlark shac policy & contract rules",
        "├── src/marketing_bot/                        # Typed Python package (strategy, mcp, cli)",
        "└── tests/                                    # 100% coverage deterministic test suite",
        "```",
        "",
        "## 6. Quality Gates & Testing (`just check`)",
        "",
        (
            "Every change is verified by `just check` (and GitHub Actions CI), "
            "running in strict order:"
        ),
        "",
        "```bash",
        "ruff format --check .",
        "ruff check .",
        "mypy --strict src tests",
        "shac test",
        "shac check --all",
        "pytest",
        "pytest",
        "```",
    ]
    return "\n".join(lines) + "\n"


def generate_daily_roundup(
    *,
    repo_root: Path,
    date_str: str,
    mentions: Sequence[MediaMention],
    strategy: MarketingStrategy,
) -> DailyRoundupPaths:
    """
    Deduplicate, score, and render the daily roundup (`roundups/YYYY-MM-DD.md`),
    per-category daily files, and updated root `README.md`.
    """
    deduped = deduplicate_mentions(mentions)
    evaluated = [evaluate_mention_positioning(m, strategy) for m in deduped]
    evaluated.sort(key=lambda x: x.relevance_score, reverse=True)

    roundup_dir = repo_root / "roundups"
    roundup_dir.mkdir(parents=True, exist_ok=True)
    roundup_file = roundup_dir / f"{date_str}.md"
    roundup_file.write_text(
        render_daily_roundup_markdown(
            date_str=date_str,
            evaluated=evaluated,
            strategy=strategy,
        ),
        encoding="utf-8",
    )

    category_files: dict[str, Path] = {}
    for category, filename in CATEGORY_DAILY_FILENAME.items():
        cat_dir = repo_root / category / date_str
        cat_dir.mkdir(parents=True, exist_ok=True)
        cat_file = cat_dir / filename
        cat_items = [item for item in evaluated if item.category == category]
        cat_file.write_text(
            render_category_daily_markdown(
                date_str=date_str,
                category=category,
                items=cat_items,
                strategy=strategy,
            ),
            encoding="utf-8",
        )
        category_files[category] = cat_file

    existing_dates: list[str] = [date_str]
    for p in roundup_dir.glob("*.md"):
        stem = p.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-" and stem not in existing_dates:
            existing_dates.append(stem)

    readme_file = repo_root / "README.md"
    readme_file.write_text(
        build_readme_markdown(
            latest_date=date_str,
            evaluated=evaluated,
            strategy=strategy,
            roundup_dates=existing_dates,
        ),
        encoding="utf-8",
    )

    return DailyRoundupPaths(
        date_str=date_str,
        roundup_file=roundup_file,
        brand_file=category_files[CATEGORY_BRAND],
        competitive_file=category_files[CATEGORY_COMPETITIVE],
        trends_file=category_files[CATEGORY_TRENDS],
        readme_file=readme_file,
    )
