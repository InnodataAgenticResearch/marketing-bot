"""
Deterministic unit test suite for `marketing_bot` achieving 100% line and branch coverage.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import marketing_bot
from marketing_bot.agility_mcp import (
    CATEGORY_BRAND,
    CATEGORY_COMPETITIVE,
    CATEGORY_TRENDS,
    AgilityMcpClient,
    HttpResponse,
    MediaMention,
    deduplicate_mentions,
    evaluate_mention_positioning,
    normalize_raw_mention,
    parse_mcp_response,
)
from marketing_bot.cli import harvest_live_mentions, main
from marketing_bot.roundup import (
    build_readme_markdown,
    default_seed_mentions,
    generate_daily_roundup,
    load_mentions_from_seed_file,
    render_category_daily_markdown,
    render_daily_roundup_markdown,
    render_evaluated_mention_block,
)
from marketing_bot.strategy import (
    default_repo_root,
    default_strategy_path,
    default_upstream_pin_path,
    format_strategy_summary,
    load_marketing_strategy,
    load_upstream_artbot_pin,
)
from tests.fakes import FakeHttpTransport


def _copy_repo_configs(tmp_path: Path) -> Path:
    """Copy UPSTREAM_ARTBOT.json and config/innodata_marketing_strategy.json into tmp_path."""
    real_root = default_repo_root()
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(real_root / "UPSTREAM_ARTBOT.json", tmp_path / "UPSTREAM_ARTBOT.json")
    shutil.copy2(
        real_root / "config" / "innodata_marketing_strategy.json",
        tmp_path / "config" / "innodata_marketing_strategy.json",
    )
    return tmp_path


def test_package_exports_and_strategy_loading(tmp_path: Path) -> None:
    assert marketing_bot.__version__ == "0.1.0"
    strategy = load_marketing_strategy()
    assert len(strategy.pillars) == 6
    assert len(strategy.accelerators) == 5
    assert len(strategy.competitor_groups) == 5
    assert len(strategy.agility_topics) >= 17

    summary = format_strategy_summary(strategy)
    assert "Innodata (NASDAQ: INOD)" in summary
    assert "6-Pillar Full-Stack Engineering Taxonomy" in summary
    assert "5 Proprietary Accelerators" in summary
    assert "Competitive Positioning Matrix" in summary

    # Test pillar, accelerator, and competitor matching helpers
    pillars = strategy.find_matching_pillars(
        "We need Agent Reliability Engineering (ARE) and microservice architecture."
    )
    assert any(p.slug == "agent-reliability-engineering" for p in pillars)
    assert any(p.slug == "software-engineering" for p in pillars)

    accelerators = strategy.find_matching_accelerators(
        "Beacon (PDF-Miner) and text-to-sql analytics for Wells Fargo."
    )
    assert any(a.slug == "beacon-pdf-miner" for a in accelerators)
    assert any(a.slug == "interactive-bi-agent" for a in accelerators)
    assert any(a.slug == "enterprise-intelligence" for a in accelerators)

    comp_by_id = strategy.find_competitor_groups(text="general article", topic_id=7640299)
    assert len(comp_by_id) == 1
    assert comp_by_id[0].slug == "scale-ai"

    comp_by_name = strategy.find_competitor_groups(text="Palantir and Mercor", topic_id=None)
    assert {g.slug for g in comp_by_name} == {"palantir", "talent-marketplaces"}

    # Validate error branches when pillars or accelerators count is wrong
    raw_data: dict[str, Any] = json.loads(default_strategy_path().read_text(encoding="utf-8"))
    bad_pillars_path = tmp_path / "bad_pillars.json"
    bad_pillars_data = dict(raw_data, pillars=raw_data["pillars"][:2])
    bad_pillars_path.write_text(json.dumps(bad_pillars_data), encoding="utf-8")
    with pytest.raises(ValueError, match="Expected 6 engineering pillars"):
        load_marketing_strategy(bad_pillars_path)

    bad_acc_path = tmp_path / "bad_acc.json"
    bad_acc_data = dict(raw_data, accelerators=raw_data["accelerators"][:2])
    bad_acc_path.write_text(json.dumps(bad_acc_data), encoding="utf-8")
    with pytest.raises(ValueError, match="Expected 5 proprietary accelerators"):
        load_marketing_strategy(bad_acc_path)


def test_upstream_artbot_pin_loading_and_validation(tmp_path: Path) -> None:
    pin = load_upstream_artbot_pin()
    assert pin["upstream_tag"] == "v0.2.0-artbot"
    assert pin["upstream_commit"] == "b3fbc3b87fd7b1e561f1d78f179ba31dcf64cb81"
    assert default_upstream_pin_path().name == "UPSTREAM_ARTBOT.json"

    bad_pin = tmp_path / "UPSTREAM_ARTBOT.json"
    bad_pin.write_text(json.dumps({"upstream_repo": "only-repo"}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field"):
        load_upstream_artbot_pin(bad_pin)


def test_parse_mcp_response_json_and_sse_and_errors() -> None:
    resp = HttpResponse(status_code=200, body='{"ok": true}')
    assert resp.json() == {"ok": True}

    direct = parse_mcp_response('{"jsonrpc": "2.0", "id": 1, "result": {"status": "ready"}}')
    assert direct["result"]["status"] == "ready"

    sse_body = (
        "event: message\n"
        "data: ping\n"
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "ad_hoc_search"}]}}\n\n'
    )
    sse_parsed = parse_mcp_response(sse_body)
    assert sse_parsed["result"]["tools"][0]["name"] == "ad_hoc_search"

    with pytest.raises(ValueError, match="Empty MCP response body"):
        parse_mcp_response("   ")

    with pytest.raises(ValueError, match="Unable to parse JSON or SSE data"):
        parse_mcp_response("event: keepalive\n: comment only\n")


def test_normalize_raw_mention_variants() -> None:
    # Epoch ms, dict outlet, explicit topic_id
    m1 = normalize_raw_mention(
        {
            "id": 99,
            "title": "Test Article",
            "url": "https://example.com/a",
            "mediaOutlet": {"name": "TechCrunch"},
            "publishedDate": 1793491200000,
            "snippet": "Snippet text",
            "sentiment": "positive",
            "mediaType": "online_news",
        },
        topic_id=7545218,
        topic_name="1. B&R - Innodata",
    )
    assert m1.mention_id == "99"
    assert m1.outlet == "TechCrunch"
    assert m1.published_date.startswith("2026-")
    assert m1.sentiment == "POSITIVE"
    assert m1.topic_id == 7545218
    assert m1.all_outlets == ("TechCrunch",)
    assert m1.all_urls == ("https://example.com/a",)

    # String outlet, short date string, fallback IDs, no URL
    m2 = normalize_raw_mention(
        {
            "title": "Fallback Title",
            "outlet_name": "Forbes",
            "published_date": "Oct 2026",
            "body": "Body fallback",
            "topic_id": "7640299",
        }
    )
    assert m2.outlet == "Forbes"
    assert m2.published_date == "Oct 2026"
    assert m2.topic_id == 7640299
    assert m2.all_urls == ()

    # Missing outlet & date fallback to defaults
    m3 = normalize_raw_mention({})
    assert m3.mention_id == "unknown"
    assert m3.outlet == "Unknown Outlet"
    assert m3.published_date == "1970-01-01"


def test_agility_mcp_client_methods_and_error_branches() -> None:
    with pytest.raises(ValueError, match="api_key is required"):
        AgilityMcpClient("   ")

    fake = FakeHttpTransport()
    # Default queue fallback when empty
    assert fake.get("https://example.com", headers={}, timeout=1.0).status_code == 200
    assert (
        fake.post_json("https://example.com", payload={}, headers={}, timeout=1.0).status_code
        == 200
    )

    client = AgilityMcpClient("test-key-123", transport=fake)

    # 1. initialize
    fake.queue_post_response(
        200,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"serverInfo": {"name": "agility-mcp"}},
            }
        ),
    )
    init_res = client.initialize()
    assert init_res["serverInfo"]["name"] == "agility-mcp"
    assert fake.post_json_calls[-1]["headers"]["apiKey"] == "test-key-123"

    # 2. list_tools (normal and non-list fallback)
    fake.queue_post_response(
        200,
        (
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"ad_hoc_search"}]}}\n'
        ),
    )
    tools = client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "ad_hoc_search"

    fake.queue_post_response(200, '{"jsonrpc":"2.0","id":2,"result":{"tools":"invalid"}}')
    assert client.list_tools() == []

    fake.queue_post_response(200, '{"jsonrpc":"2.0","id":2,"result":"non-dict"}')
    assert client.list_tools() == []

    # 3. call_ad_hoc_search: empty query validation
    with pytest.raises(ValueError, match="search_expr must not be empty"):
        client.call_ad_hoc_search("   ")

    # 4. call_ad_hoc_search via content JSON text block
    inner_json = json.dumps(
        {
            "mentions": [
                {
                    "id": "m-1",
                    "title": "Innodata Launches New Sovereign AI Suite",
                    "url": "https://example.com/inod",
                    "outlet": {"name": "Bloomberg"},
                    "publishedDate": "2026-11-01T10:00:00Z",
                    "snippet": "Innodata expands Agent Reliability Engineering.",
                }
            ]
        }
    )
    fake.queue_post_response(
        200,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": "non-json preamble"},
                        {"type": "text", "text": '{"other": 123}'},
                        {"type": "text", "text": inner_json},
                        {"type": "text", "text": "[1, 2, 3]"},
                    ]
                },
            }
        ),
    )
    mentions = client.call_ad_hoc_search('"Innodata"', areas=["HEADLINE"])
    assert len(mentions) == 1
    assert mentions[0].title == "Innodata Launches New Sovereign AI Suite"

    # 5. call_ad_hoc_search via top-level mentions + structuredContent
    fake.queue_post_response(
        200,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "mentions": [{"id": "m-2", "title": "Direct Mention"}],
                    "structuredContent": {
                        "mentions": [{"id": "m-3", "title": "Structured Mention"}]
                    },
                },
            }
        ),
    )
    both_mentions = client.call_ad_hoc_search('"Innodata"')
    assert [m.mention_id for m in both_mentions] == ["m-2", "m-3"]

    # 6. call_ad_hoc_search tool isError, RPC error, and HTTP >= 400
    fake.queue_post_response(
        200,
        json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"isError": True, "message": "bad"}}),
    )
    with pytest.raises(RuntimeError, match="ad_hoc_search returned tool error"):
        client.call_ad_hoc_search('"Innodata"')

    fake.queue_post_response(
        200,
        json.dumps({"jsonrpc": "2.0", "id": 3, "error": {"code": -32600, "message": "Invalid"}}),
    )
    with pytest.raises(RuntimeError, match="MCP RPC error"):
        client.call_ad_hoc_search('"Innodata"')

    fake.queue_post_response(502, "Bad Gateway")
    with pytest.raises(RuntimeError, match="MCP HTTP 502"):
        client.call_ad_hoc_search('"Innodata"')

    # 7. list_saved_topics (with filter, without filter, non-list, HTTP error)
    fake.queue_get_response(
        200,
        json.dumps({"topics": [{"id": 7545218, "name": "1. B&R - Innodata"}]}),
    )
    topics = client.list_saved_topics(name_filter="Innodata")
    assert len(topics) == 1
    assert "name=Innodata" in fake.get_calls[-1]["url"]

    fake.queue_get_response(200, json.dumps({"topics": "none"}))
    assert client.list_saved_topics() == []

    fake.queue_get_response(403, "Forbidden")
    with pytest.raises(RuntimeError, match="Agility REST HTTP 403"):
        client.list_saved_topics()

    # 8. search_saved_topic (int id, numeric string id, topic name string, non-list, HTTP error)
    fake.queue_post_response(
        200,
        json.dumps({"mentions": [{"id": "t-1", "title": "Saved Topic Hit"}]}),
    )
    res_int = client.search_saved_topic(7545218)
    assert len(res_int) == 1
    assert res_int[0].topic_id == 7545218

    fake.queue_post_response(
        200,
        json.dumps({"mentions": [{"id": "t-2", "title": "Digit Topic Hit"}]}),
    )
    res_digit = client.search_saved_topic("7640299")
    assert len(res_digit) == 1
    assert res_digit[0].topic_id == 7640299

    fake.queue_post_response(
        200,
        json.dumps({"mentions": [{"id": "t-3", "title": "Named Topic Hit"}]}),
    )
    res_name = client.search_saved_topic("Competitor - Scale AI")
    assert len(res_name) == 1
    assert res_name[0].topic_name == "Competitor - Scale AI"

    fake.queue_post_response(200, json.dumps({"mentions": "invalid"}))
    assert client.search_saved_topic(7545218) == []

    fake.queue_post_response(500, "Server Error")
    with pytest.raises(RuntimeError, match="Agility REST HTTP 500"):
        client.search_saved_topic(7545218)


def test_deduplicate_mentions_and_positioning_evaluation() -> None:
    m_primary = MediaMention(
        mention_id="1",
        title="Innodata Announces Sovereign Cloud Expansion - Yahoo Finance",
        url="https://finance.yahoo.com/news/inod-1",
        outlet="Yahoo Finance",
        published_date="2026-11-01",
        snippet="Short snippet.",
    )
    m_dup_headline = MediaMention(
        mention_id="2",
        title="Innodata Announces Sovereign Cloud Expansion - Reuters",
        url="https://reuters.com/news/inod-1",
        outlet="Reuters",
        published_date="2026-11-01",
        snippet="Much longer syndicated snippet covering Agent Reliability Engineering.",
        additional_outlets=("MSN",),
        additional_urls=("https://msn.com/news/inod-1",),
    )
    m_dup_url = MediaMention(
        mention_id="3",
        title="Completely Different Headline Same URL",
        url="https://finance.yahoo.com/news/inod-1",
        outlet="Yahoo Finance",
        published_date="2026-11-01",
        snippet="Short",
    )
    m_no_url_empty_title = MediaMention(
        mention_id="4",
        title="---",
        url="",
        outlet="Blog",
        published_date="2026-11-01",
        snippet="Minimal",
    )

    deduped = deduplicate_mentions([m_primary, m_dup_headline, m_dup_url, m_no_url_empty_title])
    assert len(deduped) == 2
    merged = deduped[0]
    assert merged.outlet == "Yahoo Finance"
    assert merged.additional_outlets == ("Reuters", "MSN")
    assert "https://reuters.com/news/inod-1" in merged.additional_urls
    assert "Much longer syndicated snippet" in merged.snippet

    strategy = load_marketing_strategy()

    # Evaluate BrandAndPositioning
    eval_brand = evaluate_mention_positioning(merged, strategy)
    assert eval_brand.category == CATEGORY_BRAND
    assert eval_brand.relevance_score >= 0.80

    # Evaluate CompetitiveIntelligence (with no matched pillars/accelerators to hit fallback labels)
    m_comp = MediaMention(
        mention_id="c1",
        title="Scale AI Faces Enterprise Scrutiny",
        url="https://example.com/scale",
        outlet="The Information",
        published_date="2026-11-01",
        snippet="Buyers evaluate alternatives.",
        topic_id=7640299,
    )
    eval_comp = evaluate_mention_positioning(m_comp, strategy)
    assert eval_comp.category == CATEGORY_COMPETITIVE
    assert "Scale AI" in eval_comp.matched_competitors

    # Evaluate MarketTrends
    m_trend = MediaMention(
        mention_id="t1",
        title="Enterprise Cloud Spending Rises in Q4",
        url="",
        outlet="CIO Dive",
        published_date="2026-11-01",
        snippet="",
    )
    eval_trend = evaluate_mention_positioning(m_trend, strategy)
    assert eval_trend.category == CATEGORY_TRENDS
    assert 0.15 <= eval_trend.relevance_score <= 1.0


def test_roundup_rendering_and_empty_category_branches(tmp_path: Path) -> None:
    repo = _copy_repo_configs(tmp_path)
    strategy = load_marketing_strategy(default_strategy_path(repo))

    # Pre-create an older roundup file and a non-date file in roundups/ to test archive scanning
    roundups_dir = repo / "roundups"
    roundups_dir.mkdir(parents=True, exist_ok=True)
    (roundups_dir / "2026-10-31.md").write_text("# Old roundup\n", encoding="utf-8")
    (roundups_dir / "index.md").write_text("# Non-date file\n", encoding="utf-8")

    # Test empty mentions list to cover empty states in roundup, category, and README rendering
    empty_paths = generate_daily_roundup(
        repo_root=repo,
        date_str="2026-11-01",
        mentions=[],
        strategy=strategy,
    )
    assert empty_paths.roundup_file.is_file()
    assert "_No curated signals in this category for this date._" in (
        empty_paths.roundup_file.read_text(encoding="utf-8")
    )
    assert "_No high-signal mentions recorded in this category for this date._" in (
        empty_paths.brand_file.read_text(encoding="utf-8")
    )
    assert "_No mentions recorded for the latest date._" in (
        empty_paths.readme_file.read_text(encoding="utf-8")
    )

    # Test rich mentions with syndicated URLs and no-URL mention
    seed_mentions = default_seed_mentions("2026-11-01")
    syndicated_dup = MediaMention(
        mention_id="dup-1",
        title=seed_mentions[0].title,
        url="https://syndicated.example.com/inod",
        outlet="Syndicated Wire",
        published_date="2026-11-01",
        snippet=seed_mentions[0].snippet,
    )
    no_url_mention = MediaMention(
        mention_id="no-url-1",
        title="Unlinked Market Note on Robotic Telemetry",
        url="",
        outlet="Internal Brief",
        published_date="2026-11-01",
        snippet="",
    )
    paths = generate_daily_roundup(
        repo_root=repo,
        date_str="2026-11-01",
        mentions=[*seed_mentions, syndicated_dup, no_url_mention],
        strategy=strategy,
    )
    roundup_text = paths.roundup_file.read_text(encoding="utf-8")
    assert "Syndicated URLs:" in roundup_text
    assert "Unlinked Market Note on Robotic Telemetry" in roundup_text

    readme_text = paths.readme_file.read_text(encoding="utf-8")
    assert "2026-10-31" in readme_text
    assert "## Latest Daily Market & PR Intelligence Update" in readme_text
    assert "## 6. Quality Gates & Testing (`just check`)" in readme_text

    # Direct call to render_evaluated_mention_block, render_category_daily_markdown,
    # render_daily_roundup_markdown, and build_readme_markdown without roundup_dates
    ev = evaluate_mention_positioning(no_url_mention, strategy)
    block = render_evaluated_mention_block(ev, index=1)
    assert "### 1. Unlinked Market Note" in block
    cat_md = render_category_daily_markdown(
        date_str="2026-11-01",
        category=CATEGORY_TRENDS,
        items=[ev],
        strategy=strategy,
    )
    assert "Market Trends & Buyer Demand Signals" in cat_md
    daily_md = render_daily_roundup_markdown(
        date_str="2026-11-01",
        evaluated=[ev],
        strategy=strategy,
    )
    assert "Innodata Daily Market & PR Intelligence Roundup" in daily_md
    readme_default_dates = build_readme_markdown(
        latest_date="2026-11-01",
        evaluated=[ev],
        strategy=strategy,
    )
    assert "roundups/2026-11-01.md" in readme_default_dates


def test_load_mentions_from_seed_file_formats(tmp_path: Path) -> None:
    list_file = tmp_path / "list_seed.json"
    list_file.write_text(
        json.dumps([{"id": "1", "title": "From List", "outlet": "Reuters"}]),
        encoding="utf-8",
    )
    assert len(load_mentions_from_seed_file(list_file)) == 1

    dict_file = tmp_path / "dict_seed.json"
    dict_file.write_text(
        json.dumps({"mentions": [{"id": "2", "title": "From Dict", "outlet": "WSJ"}]}),
        encoding="utf-8",
    )
    assert len(load_mentions_from_seed_file(dict_file)) == 1

    bad_file = tmp_path / "bad_seed.json"
    bad_file.write_text('"just-a-string"', encoding="utf-8")
    with pytest.raises(ValueError, match="Seed JSON must be a list"):
        load_mentions_from_seed_file(bad_file)


def test_cli_all_subcommands(tmp_path: Path) -> None:
    repo = _copy_repo_configs(tmp_path)

    # 1. upstream-status (text and --json)
    out = io.StringIO()
    err = io.StringIO()
    rc = main(["upstream-status"], repo_root=repo, stdout=out, stderr=err)
    assert rc == 0
    assert "v0.2.0-artbot" in out.getvalue()

    out_json = io.StringIO()
    rc_json = main(["upstream-status", "--json"], repo_root=repo, stdout=out_json, stderr=err)
    assert rc_json == 0
    assert json.loads(out_json.getvalue())["upstream_tag"] == "v0.2.0-artbot"

    # 2. strategy-summary
    out_strat = io.StringIO()
    rc_strat = main(["strategy-summary"], repo_root=repo, stdout=out_strat, stderr=err)
    assert rc_strat == 0
    assert "Beacon (PDF-Miner)" in out_strat.getvalue()

    # 3. mcp-search (missing key error + success with FakeHttpTransport)
    out_search = io.StringIO()
    err_search = io.StringIO()
    rc_no_key = main(
        ["mcp-search", '"Innodata"'],
        repo_root=repo,
        env={},
        stdout=out_search,
        stderr=err_search,
    )
    assert rc_no_key == 1
    assert "AGILITYPR_API_KEY is required" in err_search.getvalue()

    fake = FakeHttpTransport()
    fake.queue_post_response(
        200,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {
                    "mentions": [
                        {
                            "id": "s-1",
                            "title": "Innodata Beats Expectations on Sovereign AI Data Deals",
                            "url": "https://example.com/s1",
                            "outlet": {"name": "Barron's"},
                            "publishedDate": "2026-11-01",
                            "snippet": "Strong Agent Reliability Engineering demand.",
                        }
                    ]
                },
            }
        ),
    )
    out_search_ok = io.StringIO()
    rc_search_ok = main(
        ["mcp-search", '"Innodata"', "--page-size", "5"],
        repo_root=repo,
        transport=fake,
        env={"AGILITYPR_API_KEY": "env-key"},
        stdout=out_search_ok,
        stderr=err_search,
    )
    assert rc_search_ok == 0
    parsed_search = json.loads(out_search_ok.getvalue())
    assert parsed_search["count"] == 1
    assert parsed_search["results"][0]["category"] == CATEGORY_BRAND

    # 4. generate-daily default offline seed
    out_daily = io.StringIO()
    rc_daily = main(
        ["generate-daily", "--date", "2026-11-01"],
        repo_root=repo,
        stdout=out_daily,
        stderr=err_search,
    )
    assert rc_daily == 0
    assert (repo / "roundups" / "2026-11-01.md").is_file()

    # 5. generate-daily with --seed-file
    seed_file = tmp_path / "custom_seed.json"
    seed_file.write_text(
        json.dumps(
            [
                {
                    "id": "seed-1",
                    "title": "Palantir Pricing Scrutiny",
                    "url": "https://example.com/palantir",
                    "outlet": "TechTarget",
                    "publishedDate": "2026-11-02",
                    "snippet": "CIOs evaluate Forward Deployed Engineering alternatives.",
                }
            ]
        ),
        encoding="utf-8",
    )
    rc_seed = main(
        ["generate-daily", "--date", "2026-11-02", "--seed-file", str(seed_file)],
        repo_root=repo,
        stdout=out_daily,
        stderr=err_search,
    )
    assert rc_seed == 0
    assert (repo / "roundups" / "2026-11-02.md").is_file()

    # 6. generate-daily with --live (missing key error + success with FakeHttpTransport)
    err_live = io.StringIO()
    rc_live_no_key = main(
        ["generate-daily", "--date", "2026-11-03", "--live"],
        repo_root=repo,
        env={},
        stdout=out_daily,
        stderr=err_live,
    )
    assert rc_live_no_key == 1
    assert "AGILITYPR_API_KEY is required for --live" in err_live.getvalue()

    live_fake = FakeHttpTransport()
    live_fake.queue_post_response(
        200,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {"mentions": [{"id": "live-1", "title": "Innodata Live MCP Hit"}]},
            }
        ),
    )
    strategy = load_marketing_strategy(default_strategy_path(repo))
    for topic in strategy.agility_topics:
        live_fake.queue_post_response(
            200,
            json.dumps(
                {
                    "mentions": [
                        {
                            "id": f"topic-{topic.topic_id}",
                            "title": f"Update for {topic.name}",
                            "publishedDate": "2026-11-03",
                        }
                    ]
                }
            ),
        )
    rc_live_ok = main(
        ["generate-daily", "--date", "2026-11-03", "--live", "--api-key", "direct-key"],
        repo_root=repo,
        transport=live_fake,
        stdout=out_daily,
        stderr=err_live,
    )
    assert rc_live_ok == 0
    assert (repo / "roundups" / "2026-11-03.md").is_file()

    # Verify harvest_live_mentions directly as well
    client = AgilityMcpClient("direct-key", transport=FakeHttpTransport())
    harvested = harvest_live_mentions(client, strategy)
    assert harvested == []
