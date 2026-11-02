"""Validate model proposals against one actual text slice before graph construction."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Entity:
    kind: str
    label: str
    start: int
    end: int


@dataclass(frozen=True)
class Claim:
    source: str | int
    target: int
    predicate: str
    start: int
    end: int


def validate_extraction(text: str, proposal: Any) -> tuple[list[Entity], list[Claim]]:
    """Accept only closed-schema entities and relations with verifiable source spans."""
    if not isinstance(proposal, dict) or set(proposal) != {"entities", "claims"}:
        raise ValueError("invalid extraction")
    entities, claims = proposal["entities"], proposal["claims"]
    if not isinstance(entities, list) or not isinstance(claims, list):
        raise ValueError("invalid extraction")
    if len(entities) > 100 or len(claims) > 200:
        raise ValueError("extraction limit exceeded")
    result_entities = []
    for item in entities:
        if not isinstance(item, dict) or set(item) != {"kind", "label", "start", "end"}:
            raise ValueError("invalid entity")
        start, end, label, kind = item["start"], item["end"], item["label"], item["kind"]
        if (
            not isinstance(kind, str)
            or kind not in {"concept", "method", "dataset", "keyword"}
            or not isinstance(label, str)
            or not label.strip()
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or text[start:end] != label
        ):
            raise ValueError("entity lacks actual text support")
        result_entities.append(Entity(kind, label, start, end))
    result_claims = []
    for item in claims:
        if not isinstance(item, dict) or set(item) != {
            "source",
            "target",
            "predicate",
            "start",
            "end",
            "quote",
        }:
            raise ValueError("invalid claim")
        source, target, predicate = item["source"], item["target"], item["predicate"]
        start, end, quote = item["start"], item["end"], item["quote"]
        if (
            type(target) is not int
            or not 0 <= target < len(result_entities)
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or not isinstance(quote, str)
            or text[start:end] != quote
        ):
            raise ValueError("claim lacks actual text support")
        target_entity = result_entities[target]
        if not (start <= target_entity.start and target_entity.end <= end):
            raise ValueError("claim support does not contain target")
        if predicate == "mentions":
            valid = (
                isinstance(source, str)
                and source in {"asset", "chunk"}
                and target_entity.kind in {"concept", "keyword"}
            )
        elif isinstance(predicate, str) and predicate in {"uses_method", "uses_dataset"}:
            valid = source == "asset" and target_entity.kind == predicate.removeprefix("uses_")
        elif predicate == "related_to":
            valid = (
                type(source) is int
                and 0 <= source < len(result_entities)
                and result_entities[source].kind in {"concept", "method", "dataset"}
                and target_entity.kind in {"concept", "method", "dataset"}
                and start <= result_entities[source].start
                and result_entities[source].end <= end
            )
        else:
            valid = False
        if not valid:
            raise ValueError("invalid relation")
        result_claims.append(Claim(source, target, predicate, start, end))
    return result_entities, result_claims
