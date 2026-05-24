from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from typing import Any

from ..errors import AgentError, ErrorCode
from ..util.cache import snapshot_cache
from .tree import UiNode

log = logging.getLogger(__name__)


@dataclass
class Resolution:
    strategy: str          # "id" | "resource_id" | "text" | "composite" | "coords"
    node: UiNode | None
    x: int
    y: int
    candidates_considered: int


def _text_sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _score_node(node: UiNode, sel: dict) -> int:
    score = 0

    rid = sel.get("resource_id")
    if rid and node.resource_id == rid:
        score += 10

    text = sel.get("text")
    if text and node.text == text:
        score += 6
    elif text and _text_sim(node.text, text) > 0.85:
        score += 4

    text_contains = sel.get("text_contains")
    if text_contains and text_contains.lower() in node.text.lower():
        score += 2

    desc = sel.get("content_desc")
    if desc and node.content_desc == desc:
        score += 4
    elif desc and _text_sim(node.content_desc, desc) > 0.85:
        score += 2

    cls = sel.get("class")
    if cls and cls in node.cls:
        score += 3

    pkg = sel.get("package")
    if pkg and node.package == pkg:
        score += 1

    # Clickable bonus only breaks ties when a semantic match already occurred.
    if score > 0 and node.clickable:
        score += 1

    return score


def resolve(
    selector: dict[str, Any],
    serial: str,
    fallback_x: int | None = None,
    fallback_y: int | None = None,
) -> Resolution:
    """Resolve a semantic selector against the last snapshot for the given device."""

    # --- Fast path: SoM id ---
    som_id = selector.get("id")
    if som_id is not None:
        snap = snapshot_cache.get(serial)
        if snap:
            for node in snap.nodes:
                if node.id == som_id:
                    return Resolution(
                        strategy="id",
                        node=node,
                        x=node.center["x"],
                        y=node.center["y"],
                        candidates_considered=len(snap.nodes),
                    )
        # SoM id given but cache miss — fall through to fresh hierarchy.

    # --- Use cached nodes or require caller to have refreshed ---
    snap = snapshot_cache.get(serial)
    if snap is None:
        # No snapshot at all — fallback to coords if provided.
        if fallback_x is not None and fallback_y is not None:
            return Resolution(
                strategy="coords",
                node=None,
                x=fallback_x,
                y=fallback_y,
                candidates_considered=0,
            )
        raise AgentError(
            ErrorCode.HIERARCHY_STALE,
            "No UI snapshot available for this device.",
            hint="Call get_screen first to capture the current UI state.",
        )

    nodes = snap.nodes
    clickable_only = selector.get("clickable_only", True)
    candidates = nodes if not clickable_only else [n for n in nodes if n.clickable or n.long_clickable]

    # Score each candidate.
    scored: list[tuple[int, UiNode]] = []
    for node in candidates:
        s = _score_node(node, selector)
        if s > 0:
            scored.append((s, node))

    if not scored:
        # Coords fallback.
        if fallback_x is not None and fallback_y is not None:
            return Resolution(
                strategy="coords",
                node=None,
                x=fallback_x,
                y=fallback_y,
                candidates_considered=len(candidates),
            )
        raise AgentError(
            ErrorCode.SELECTOR_NO_MATCH,
            f"No element matched selector {selector}.",
            hint="Call get_screen to refresh the UI tree, or check selector keys.",
            extra={"selector": selector},
        )

    scored.sort(key=lambda t: t[0], reverse=True)
    top_score = scored[0][0]
    tied = [node for s, node in scored if s == top_score]

    explicit_index = selector.get("index")  # None when caller did not supply it
    if len(tied) == 1:
        chosen = tied[0]
    elif explicit_index is not None and explicit_index < len(tied):
        chosen = tied[explicit_index]
    else:
        # Multiple matches with equal score and no explicit index — ambiguous.
        top3 = [
            {"id": n.id, "text": n.text, "content_desc": n.content_desc, "resource_id": n.resource_id}
            for _, n in scored[:3]
        ]
        raise AgentError(
            ErrorCode.SELECTOR_AMBIGUOUS,
            f"Selector matched {len(tied)} elements with equal score.",
            hint="Narrow with resource_id or pass index:N to pick the Nth match.",
            extra={"candidates": top3, "selector": selector},
        )

    strategy = "id" if som_id is not None else ("resource_id" if selector.get("resource_id") else "text")
    return Resolution(
        strategy=strategy,
        node=chosen,
        x=chosen.center["x"],
        y=chosen.center["y"],
        candidates_considered=len(candidates),
    )
