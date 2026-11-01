"""
Innodata Enterprise AI Strategy model, 6-pillar taxonomy, 5 proprietary accelerators,
GTM playbook, competitive differentiation matrix, and Agility PR topic catalog.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineeringPillar:
    """One of Innodata's 6 full-stack enterprise AI engineering pillars."""

    slug: str
    name: str
    description: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class ProprietaryAccelerator:
    """One of Innodata's 5 proprietary production AI accelerators."""

    slug: str
    name: str
    description: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class GtmPlaybook:
    """Innodata's Go-To-Market playbook for solving Pilot Purgatory."""

    primary_wedge: str
    expansion_motion: str
    lock_in_stance: str
    target_triggers: tuple[str, ...]


@dataclass(frozen=True)
class CompetitorGroup:
    """Competitive cohort, weakness, and Innodata's differentiation counter."""

    slug: str
    label: str
    competitors: tuple[str, ...]
    topic_ids: tuple[int, ...]
    weakness: str
    innodata_counter: str
    evergreen_path: str


@dataclass(frozen=True)
class AgilityTopicSpec:
    """Saved topic metadata in Agility PR Media Intelligence."""

    topic_id: int
    name: str
    category: str
    evergreen_path: str


@dataclass(frozen=True)
class MarketingStrategy:
    """Complete Innodata Enterprise AI Marketing & PR Strategy configuration."""

    company: str
    core_positioning: str
    value_proposition: str
    sovereign_clouds: tuple[str, ...]
    pillars: tuple[EngineeringPillar, ...]
    accelerators: tuple[ProprietaryAccelerator, ...]
    gtm_playbook: GtmPlaybook
    competitor_groups: tuple[CompetitorGroup, ...]
    agility_topics: tuple[AgilityTopicSpec, ...]

    def find_competitor_groups(
        self,
        *,
        text: str,
        topic_id: int | None = None,
    ) -> tuple[CompetitorGroup, ...]:
        """Return competitor groups matching either `topic_id` or competitor names in `text`."""
        lowered = text.lower()
        matched: list[CompetitorGroup] = []
        for group in self.competitor_groups:
            id_match = topic_id is not None and topic_id in group.topic_ids
            name_match = any(comp.lower() in lowered for comp in group.competitors)
            if id_match or name_match:
                matched.append(group)
        return tuple(matched)

    def find_matching_pillars(self, text: str) -> tuple[EngineeringPillar, ...]:
        """Return engineering pillars whose name or keywords appear in `text`."""
        lowered = text.lower()
        matched: list[EngineeringPillar] = []
        for pillar in self.pillars:
            if pillar.name.lower() in lowered or any(
                kw.lower() in lowered for kw in pillar.keywords
            ):
                matched.append(pillar)
        return tuple(matched)

    def find_matching_accelerators(self, text: str) -> tuple[ProprietaryAccelerator, ...]:
        """Return proprietary accelerators whose name or keywords appear in `text`."""
        lowered = text.lower()
        matched: list[ProprietaryAccelerator] = []
        for acc in self.accelerators:
            if acc.name.lower() in lowered or any(kw.lower() in lowered for kw in acc.keywords):
                matched.append(acc)
        return tuple(matched)


def default_repo_root() -> Path:
    """Resolve the repository root directory relative to this package."""
    return Path(__file__).resolve().parents[2]


def default_strategy_path(repo_root: Path | None = None) -> Path:
    """Return path to `config/innodata_marketing_strategy.json`."""
    root = default_repo_root() if repo_root is None else repo_root
    return root / "config" / "innodata_marketing_strategy.json"


def default_upstream_pin_path(repo_root: Path | None = None) -> Path:
    """Return path to `UPSTREAM_ARTBOT.json`."""
    root = default_repo_root() if repo_root is None else repo_root
    return root / "UPSTREAM_ARTBOT.json"


def load_marketing_strategy(path: Path | None = None) -> MarketingStrategy:
    """Load and validate Innodata's marketing strategy JSON configuration."""
    target = default_strategy_path() if path is None else path
    raw: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))

    pillars = tuple(
        EngineeringPillar(
            slug=str(item["slug"]),
            name=str(item["name"]),
            description=str(item["description"]),
            keywords=tuple(str(k) for k in item["keywords"]),
        )
        for item in raw["pillars"]
    )
    accelerators = tuple(
        ProprietaryAccelerator(
            slug=str(item["slug"]),
            name=str(item["name"]),
            description=str(item["description"]),
            keywords=tuple(str(k) for k in item["keywords"]),
        )
        for item in raw["accelerators"]
    )
    gtm_raw = raw["gtm_playbook"]
    gtm_playbook = GtmPlaybook(
        primary_wedge=str(gtm_raw["primary_wedge"]),
        expansion_motion=str(gtm_raw["expansion_motion"]),
        lock_in_stance=str(gtm_raw["lock_in_stance"]),
        target_triggers=tuple(str(t) for t in gtm_raw["target_triggers"]),
    )
    competitor_groups = tuple(
        CompetitorGroup(
            slug=str(item["slug"]),
            label=str(item["label"]),
            competitors=tuple(str(c) for c in item["competitors"]),
            topic_ids=tuple(int(tid) for tid in item["topic_ids"]),
            weakness=str(item["weakness"]),
            innodata_counter=str(item["innodata_counter"]),
            evergreen_path=str(item["evergreen_path"]),
        )
        for item in raw["competitor_groups"]
    )
    agility_topics = tuple(
        AgilityTopicSpec(
            topic_id=int(item["topic_id"]),
            name=str(item["name"]),
            category=str(item["category"]),
            evergreen_path=str(item["evergreen_path"]),
        )
        for item in raw["agility_topics"]
    )

    if len(pillars) != 6:
        raise ValueError(f"Expected 6 engineering pillars, found {len(pillars)}")
    if len(accelerators) != 5:
        raise ValueError(f"Expected 5 proprietary accelerators, found {len(accelerators)}")

    return MarketingStrategy(
        company=str(raw["company"]),
        core_positioning=str(raw["core_positioning"]),
        value_proposition=str(raw["value_proposition"]),
        sovereign_clouds=tuple(str(c) for c in raw["sovereign_clouds"]),
        pillars=pillars,
        accelerators=accelerators,
        gtm_playbook=gtm_playbook,
        competitor_groups=competitor_groups,
        agility_topics=agility_topics,
    )


def load_upstream_artbot_pin(path: Path | None = None) -> dict[str, Any]:
    """Load and verify the upstream ArtBOT release pin (`UPSTREAM_ARTBOT.json`)."""
    target = default_upstream_pin_path() if path is None else path
    data: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    for key in ("upstream_repo", "upstream_tag", "upstream_commit", "public_api_allowlist"):
        if key not in data or not data[key]:
            raise ValueError(f"UPSTREAM_ARTBOT.json missing required field '{key}'")
    return data


def format_strategy_summary(strategy: MarketingStrategy) -> str:
    """Format a human-readable Markdown summary of Innodata's marketing strategy."""
    lines: list[str] = [
        f"# {strategy.company} — Enterprise AI Marketing & PR Strategy",
        "",
        f"**Positioning:** {strategy.core_positioning}",
        f"**Sovereign Clouds:** {', '.join(strategy.sovereign_clouds)}",
        f"**Primary GTM Wedge:** {strategy.gtm_playbook.primary_wedge}",
        "",
        "## 6-Pillar Full-Stack Engineering Taxonomy",
    ]
    for idx, pillar in enumerate(strategy.pillars, 1):
        lines.append(f"{idx}. **{pillar.name}** — {pillar.description}")
    lines.append("")
    lines.append("## 5 Proprietary Accelerators")
    for idx, acc in enumerate(strategy.accelerators, 1):
        lines.append(f"{idx}. **{acc.name}** — {acc.description}")
    lines.append("")
    lines.append("## Competitive Positioning Matrix")
    for group in strategy.competitor_groups:
        comps = ", ".join(group.competitors)
        lines.append(f"- **{group.label}** ({comps}): {group.innodata_counter}")
    return "\n".join(lines)
