"""
Agility PR MCP Server (`https://apigateway.agilitypr.com/api/mcp`) and REST API
(`https://mediaintelligence.agilitypr.com/api/v1`) client, mention deduplicator,
and Innodata Enterprise AI positioning evaluator.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from marketing_bot.strategy import MarketingStrategy

DEFAULT_MCP_URL = "https://apigateway.agilitypr.com/api/mcp"
DEFAULT_REST_BASE_URL = "https://mediaintelligence.agilitypr.com/api/v1"

CATEGORY_BRAND = "BrandAndPositioning"
CATEGORY_COMPETITIVE = "CompetitiveIntelligence"
CATEGORY_TRENDS = "MarketTrends"
INTELLIGENCE_CATEGORIES: tuple[str, ...] = (
    CATEGORY_BRAND,
    CATEGORY_COMPETITIVE,
    CATEGORY_TRENDS,
)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TRAILING_OUTLET_RE = re.compile(r"\s+[-|]\s+[A-Z][\w\s.&'-]{1,40}$")


@dataclass(frozen=True)
class HttpResponse:
    """Minimal HTTP response object for deterministic testing and transports."""

    status_code: int
    body: str

    def json(self) -> dict[str, Any]:
        """Parse JSON response body."""
        res: dict[str, Any] = json.loads(self.body)
        return res


class HttpTransport(Protocol):
    """Protocol for injectable HTTP transports."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...  # pragma: no cover - protocol stub

    def post_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse: ...  # pragma: no cover - protocol stub


class UrllibHttpTransport:
    """Standard-library urllib transport implementing `HttpTransport`."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse:  # pragma: no cover - network transport boundary
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(
                    status_code=int(resp.status),
                    body=resp.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status_code=int(exc.code),
                body=exc.read().decode("utf-8", errors="replace"),
            )

    def post_json(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> HttpResponse:  # pragma: no cover - network transport boundary
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(
                    status_code=int(resp.status),
                    body=resp.read().decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status_code=int(exc.code),
                body=exc.read().decode("utf-8", errors="replace"),
            )


@dataclass(frozen=True)
class MediaMention:
    """Normalized media mention from Agility PR MCP or REST API."""

    mention_id: str
    title: str
    url: str
    outlet: str
    published_date: str
    snippet: str
    sentiment: str = "NEUTRAL"
    media_type: str = "ONLINE_NEWS"
    topic_id: int | None = None
    topic_name: str = ""
    additional_outlets: tuple[str, ...] = ()
    additional_urls: tuple[str, ...] = ()

    @property
    def all_outlets(self) -> tuple[str, ...]:
        """Return primary outlet followed by any deduplicated syndication outlets."""
        return (self.outlet, *self.additional_outlets)

    @property
    def all_urls(self) -> tuple[str, ...]:
        """Return primary URL followed by any deduplicated syndication URLs."""
        if not self.url:
            return self.additional_urls
        return (self.url, *self.additional_urls)


@dataclass(frozen=True)
class EvaluatedMention:
    """Media mention scored and classified against Innodata's Enterprise AI Strategy."""

    mention: MediaMention
    category: str
    relevance_score: float
    matched_pillars: tuple[str, ...]
    matched_accelerators: tuple[str, ...]
    matched_competitors: tuple[str, ...]
    why_it_matters: str
    positioning_angle: str
    recommended_action: str


def parse_mcp_response(raw_body: str) -> dict[str, Any]:
    """
    Parse a Streamable HTTP JSON-RPC 2.0 response from Agility PR MCP (`POST /api/mcp`),
    supporting both plain `application/json` bodies and `text/event-stream` (`data: {...}`).
    """
    stripped = raw_body.strip()
    if not stripped:
        raise ValueError("Empty MCP response body")

    if stripped.startswith("{"):
        parsed_json: dict[str, Any] = json.loads(stripped)
        return parsed_json

    data_objects: list[dict[str, Any]] = []
    for line in stripped.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("data:"):
            payload_text = line_clean[len("data:") :].strip()
            if payload_text and payload_text.startswith("{"):
                obj: dict[str, Any] = json.loads(payload_text)
                data_objects.append(obj)

    if not data_objects:
        raise ValueError(f"Unable to parse JSON or SSE data from MCP body: {stripped[:160]}")

    return data_objects[-1]


def _format_published_date(raw_value: Any) -> str:
    """Convert epoch milliseconds or ISO timestamp into `YYYY-MM-DD`."""
    if isinstance(raw_value, (int, float)) and raw_value > 0:
        dt = datetime.fromtimestamp(float(raw_value) / 1000.0, tz=UTC)
        return dt.strftime("%Y-%m-%d")
    if isinstance(raw_value, str) and raw_value.strip():
        clean = raw_value.strip()
        if len(clean) >= 10 and clean[4] == "-" and clean[7] == "-":
            return clean[:10]
        return clean
    return "1970-01-01"


def normalize_raw_mention(
    raw: dict[str, Any],
    *,
    topic_id: int | None = None,
    topic_name: str = "",
) -> MediaMention:
    """Normalize a raw Agility PR mention dictionary into a `MediaMention`."""
    mention_id = str(
        raw.get("id")
        or raw.get("mentionId")
        or raw.get("syndicationId")
        or raw.get("url")
        or raw.get("title")
        or "unknown"
    )
    title = str(raw.get("title") or "Untitled Mention").strip()
    url = str(raw.get("url") or "").strip()

    outlet_val = raw.get("outlet") or raw.get("mediaOutlet") or raw.get("outlet_name")
    if isinstance(outlet_val, dict):
        outlet = str(outlet_val.get("name") or "Unknown Outlet").strip()
    elif isinstance(outlet_val, str) and outlet_val.strip():
        outlet = outlet_val.strip()
    else:
        outlet = "Unknown Outlet"

    published_date = _format_published_date(
        raw.get("publishedDate") or raw.get("published_date") or raw.get("published_at")
    )
    snippet = str(raw.get("snippet") or raw.get("body") or raw.get("contentSnippet") or "").strip()
    sentiment = str(raw.get("sentiment") or "NEUTRAL").strip().upper()
    media_type = str(raw.get("mediaType") or raw.get("media_type") or "ONLINE_NEWS").strip().upper()

    resolved_topic_id = topic_id
    if resolved_topic_id is None and raw.get("topic_id") is not None:
        resolved_topic_id = int(raw["topic_id"])
    resolved_topic_name = topic_name or str(raw.get("topic_name") or "").strip()

    return MediaMention(
        mention_id=mention_id,
        title=title,
        url=url,
        outlet=outlet,
        published_date=published_date,
        snippet=snippet,
        sentiment=sentiment,
        media_type=media_type,
        topic_id=resolved_topic_id,
        topic_name=resolved_topic_name,
    )


class AgilityMcpClient:
    """
    Dependency-injected client for the Agility PR MCP Server (`/api/mcp`) and
    Agility PR Media Intelligence REST API (`/api/v1`).
    """

    def __init__(
        self,
        api_key: str,
        *,
        transport: HttpTransport | None = None,
        mcp_url: str = DEFAULT_MCP_URL,
        rest_base_url: str = DEFAULT_REST_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        cleaned_key = api_key.strip()
        if not cleaned_key:
            raise ValueError("api_key is required for AgilityMcpClient")
        self.api_key = cleaned_key
        self.transport: HttpTransport = (
            UrllibHttpTransport()
            if transport is None
            else transport  # pragma: no cover - default runtime wiring
        )
        self.mcp_url = mcp_url
        self.rest_base_url = rest_base_url.rstrip("/")
        self.timeout = timeout

    def _mcp_headers(self) -> dict[str, str]:
        return {
            "apiKey": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def _rest_headers(self) -> dict[str, str]:
        return {
            "apiKey": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _rpc_call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: int = 1,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": {} if params is None else params,
        }
        resp = self.transport.post_json(
            self.mcp_url,
            payload=payload,
            headers=self._mcp_headers(),
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"MCP HTTP {resp.status_code}: {resp.body}")
        parsed = parse_mcp_response(resp.body)
        if parsed.get("error"):
            raise RuntimeError(f"MCP RPC error: {parsed['error']}")
        result = parsed.get("result")
        if isinstance(result, dict):
            return result
        return {}

    def initialize(self) -> dict[str, Any]:
        """Execute JSON-RPC 2.0 `initialize` handshake against Agility PR MCP."""
        return self._rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "marketing-bot", "version": "0.1.0"},
            },
            request_id=1,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """Execute JSON-RPC 2.0 `tools/list` against Agility PR MCP."""
        result = self._rpc_call("tools/list", {}, request_id=2)
        tools = result.get("tools", [])
        if isinstance(tools, list):
            return [t for t in tools if isinstance(t, dict)]
        return []

    def call_ad_hoc_search(
        self,
        search_expr: str,
        *,
        date_range: str = "LAST_7_DAYS",
        areas: list[str] | None = None,
        page_size: int = 25,
        topic_name: str = "MCP ad_hoc_search",
    ) -> list[MediaMention]:
        """
        Invoke the `ad_hoc_search` MCP tool using Agility PR's Expert Search boolean syntax.
        """
        cleaned_expr = search_expr.strip()
        if not cleaned_expr:
            raise ValueError("search_expr must not be empty")

        result = self._rpc_call(
            "tools/call",
            {
                "name": "ad_hoc_search",
                "arguments": {
                    "search": cleaned_expr,
                    "dateRange": date_range,
                    "areas": ["HEADLINE", "LEAD", "BODY"] if areas is None else areas,
                    "pageSize": page_size,
                },
            },
            request_id=3,
        )

        if result.get("isError"):
            raise RuntimeError(f"ad_hoc_search returned tool error: {result}")

        raw_mentions: list[dict[str, Any]] = []
        if isinstance(result.get("mentions"), list):
            raw_mentions.extend(m for m in result["mentions"] if isinstance(m, dict))
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and isinstance(structured.get("mentions"), list):
            raw_mentions.extend(m for m in structured["mentions"] if isinstance(m, dict))

        content_blocks = result.get("content")
        if not raw_mentions and isinstance(content_blocks, list):
            for block in content_blocks:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    text_val = block["text"].strip()
                    if text_val.startswith("{"):
                        decoded = json.loads(text_val)
                        if isinstance(decoded, dict) and isinstance(decoded.get("mentions"), list):
                            raw_mentions.extend(
                                m for m in decoded["mentions"] if isinstance(m, dict)
                            )

        return [normalize_raw_mention(m, topic_name=topic_name) for m in raw_mentions]

    def list_saved_topics(self, *, name_filter: str | None = None) -> list[dict[str, Any]]:
        """List saved topics via `GET /api/v1/topic`."""
        url = f"{self.rest_base_url}/topic"
        if name_filter:
            url = f"{url}?name={urllib.parse.quote(name_filter)}"
        resp = self.transport.get(
            url,
            headers=self._rest_headers(),
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Agility REST HTTP {resp.status_code}: {resp.body}")
        data = resp.json()
        topics = data.get("topics", [])
        if isinstance(topics, list):
            return [t for t in topics if isinstance(t, dict)]
        return []

    def search_saved_topic(
        self,
        topic: int | str,
        *,
        date_range: str = "LAST_7_DAYS",
        page: int = 1,
        page_size: int = 25,
        topic_name: str = "",
    ) -> list[MediaMention]:
        """Search mentions within a saved topic via `POST /api/v1/topic/search`."""
        payload: dict[str, Any] = {
            "publicationDate": {"relative": date_range},
            "paginationParams": {
                "page": page,
                "pageSize": page_size,
                "sortField": "PUBLISHED_DATE",
                "sortOrder": "DESCENDING",
            },
        }
        resolved_topic_id: int | None = None
        if isinstance(topic, int):
            payload["id"] = topic
            resolved_topic_id = topic
        elif topic.isdigit():
            resolved_topic_id = int(topic)
            payload["id"] = resolved_topic_id
        else:
            payload["name"] = topic

        resp = self.transport.post_json(
            f"{self.rest_base_url}/topic/search",
            payload=payload,
            headers=self._rest_headers(),
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Agility REST HTTP {resp.status_code}: {resp.body}")
        data = resp.json()
        mentions = data.get("mentions", [])
        if not isinstance(mentions, list):
            return []
        label = topic_name or (str(topic) if not isinstance(topic, int) else f"Topic {topic}")
        return [
            normalize_raw_mention(m, topic_id=resolved_topic_id, topic_name=label)
            for m in mentions
            if isinstance(m, dict)
        ]


def _canonical_headline(title: str) -> str:
    """Normalize headline text for syndication deduplication."""
    stripped_suffix = _TRAILING_OUTLET_RE.sub("", title.strip())
    return _NON_ALNUM_RE.sub(" ", stripped_suffix.lower()).strip()


def deduplicate_mentions(mentions: Sequence[MediaMention]) -> list[MediaMention]:
    """
    Collapse syndicated or duplicate mentions sharing a normalized headline or URL
    into a single `MediaMention` with combined `additional_outlets` and `additional_urls`.
    """
    deduped: list[MediaMention] = []
    headline_index: dict[str, int] = {}
    url_index: dict[str, int] = {}

    for item in mentions:
        h_key = _canonical_headline(item.title)
        u_key = item.url.strip().lower()

        existing_idx: int | None = None
        if u_key and u_key in url_index:
            existing_idx = url_index[u_key]
        elif h_key and h_key in headline_index:
            existing_idx = headline_index[h_key]

        if existing_idx is None:
            idx = len(deduped)
            deduped.append(item)
            if h_key:
                headline_index[h_key] = idx
            if u_key:
                url_index[u_key] = idx
            continue

        current = deduped[existing_idx]
        merged_outlets = list(current.additional_outlets)
        for cand_outlet in (item.outlet, *item.additional_outlets):
            if cand_outlet and cand_outlet != current.outlet and cand_outlet not in merged_outlets:
                merged_outlets.append(cand_outlet)

        merged_urls = list(current.additional_urls)
        for cand_url in (item.url, *item.additional_urls):
            if cand_url and cand_url != current.url and cand_url not in merged_urls:
                merged_urls.append(cand_url)

        best_snippet = item.snippet if len(item.snippet) > len(current.snippet) else current.snippet
        updated = replace(
            current,
            snippet=best_snippet,
            additional_outlets=tuple(merged_outlets),
            additional_urls=tuple(merged_urls),
        )
        deduped[existing_idx] = updated
        if u_key:
            url_index[u_key] = existing_idx

    return deduped


def evaluate_mention_positioning(
    mention: MediaMention,
    strategy: MarketingStrategy,
) -> EvaluatedMention:
    """
    Score (`0.00`–`1.00`), classify (`BrandAndPositioning`, `CompetitiveIntelligence`,
    or `MarketTrends`), and generate actionable GTM/PR intelligence for a mention.
    """
    combined = f"{mention.title} {mention.snippet} {mention.topic_name}"
    lowered = combined.lower()

    matched_groups = strategy.find_competitor_groups(text=combined, topic_id=mention.topic_id)
    matched_competitors: list[str] = []
    for group in matched_groups:
        for comp in group.competitors:
            if (
                comp.lower() in lowered
                or (mention.topic_id is not None and mention.topic_id in group.topic_ids)
            ) and comp not in matched_competitors:
                matched_competitors.append(comp)

    matched_pillars = tuple(p.name for p in strategy.find_matching_pillars(combined))
    matched_accelerators = tuple(a.name for a in strategy.find_matching_accelerators(combined))

    is_direct_brand = (
        "innodata" in lowered or "nasdaq: inod" in lowered or mention.topic_id == 7545218
    )
    has_positioning_theme = any(
        phrase in lowered
        for phrase in (
            "pilot purgatory",
            "agent reliability",
            "forward deployed",
            "de-risking",
            "sovereign cloud",
        )
    )

    if matched_groups and not (is_direct_brand and not matched_competitors):
        category = CATEGORY_COMPETITIVE
    elif is_direct_brand or has_positioning_theme:
        category = CATEGORY_BRAND
    else:
        category = CATEGORY_TRENDS

    score = 0.35
    if is_direct_brand:
        score += 0.35
    if matched_groups:
        score += 0.25
    if matched_pillars:
        score += min(0.30, 0.12 * len(matched_pillars))
    if matched_accelerators:
        score += min(0.25, 0.15 * len(matched_accelerators))
    if any(
        kw in lowered
        for kw in (
            "pilot purgatory",
            "roi",
            "hallucination",
            "red teaming",
            "sovereign",
            "agentic",
            "consolidation",
        )
    ):
        score += 0.10

    clamped_score = round(min(1.0, max(0.15, score)), 2)

    pillars_label = (
        ", ".join(matched_pillars)
        if matched_pillars
        else "Agent Engineering & Agent Reliability Engineering (ARE)"
    )
    accel_label = (
        ", ".join(matched_accelerators)
        if matched_accelerators
        else "Enterprise Intelligence & Analysis CoPilot"
    )

    if category == CATEGORY_COMPETITIVE and matched_groups:
        primary_group = matched_groups[0]
        comp_names = ", ".join(matched_competitors or primary_group.competitors)
        why_it_matters = (
            f"Active coverage on {comp_names} ({primary_group.label}) exposes buyer sensitivity "
            f"around {primary_group.weakness.lower()}"
        )
        positioning_angle = (
            f"Position {strategy.company} against {comp_names}: {primary_group.innodata_counter} "
            f"Highlight our {pillars_label} capabilities."
        )
        recommended_action = (
            f"Equip SDR and executive GTM teams with a rapid counter-narrative targeting "
            f"{comp_names} accounts using {accel_label} as a 2-4 week production POC wedge."
        )
    elif category == CATEGORY_BRAND:
        why_it_matters = (
            f"Directly reinforces {strategy.company}'s core positioning around "
            f"{pillars_label} and Accelerator-Led De-Risking in sovereign clouds "
            f"({', '.join(strategy.sovereign_clouds)})."
        )
        positioning_angle = (
            f"{strategy.gtm_playbook.primary_wedge} — {strategy.gtm_playbook.expansion_motion} "
            f"with {strategy.gtm_playbook.lock_in_stance.lower()}."
        )
        recommended_action = (
            f"Amplify across executive LinkedIn and analyst briefings, anchoring on "
            f"{accel_label} and deterministic Agent Reliability Engineering (ARE) gates."
        )
    else:
        why_it_matters = (
            f"Signals enterprise demand across {pillars_label} where buyers struggle to move "
            f"GenAI from experimental pilots into deterministic production."
        )
        positioning_angle = (
            f"Bridge raw foundation models to sovereign production using {strategy.company}'s "
            f"full-stack taxonomy ({pillars_label}) and {accel_label}."
        )
        recommended_action = (
            f"Publish a rapid-response commentary and SDR outbound trigger play connecting "
            f"this market trend to {strategy.gtm_playbook.primary_wedge}."
        )

    return EvaluatedMention(
        mention=mention,
        category=category,
        relevance_score=clamped_score,
        matched_pillars=matched_pillars,
        matched_accelerators=matched_accelerators,
        matched_competitors=tuple(matched_competitors),
        why_it_matters=why_it_matters,
        positioning_angle=positioning_angle,
        recommended_action=recommended_action,
    )
