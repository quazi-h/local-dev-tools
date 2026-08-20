"""Local-first definition lookups for the Definition Finder command."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DICTIONARY_API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/"

TECH_DEFINITIONS: dict[str, str] = {
    "acid": "A set of transaction guarantees: atomicity, consistency, isolation, and durability.",
    "api": "An application programming interface: a defined way for software components to communicate.",
    "backfill": "A retrospective data-processing run that fills historical records using current logic.",
    "cache": "A fast, temporary store that retains reusable data to avoid repeated expensive work.",
    "ci": "Continuous integration: automatically building and testing changes as they are merged.",
    "compiler": "A program that translates source code into another executable or lower-level form.",
    "concurrency": "Multiple tasks making progress during overlapping periods of time.",
    "consistency": "The guarantee that reads observe data according to a specified correctness model.",
    "container": "An isolated software package containing an application and its runtime dependencies.",
    "data warehouse": "A system designed to store integrated historical data for analysis and reporting.",
    "database": "An organized system for storing, retrieving, and managing persistent data.",
    "denormalization": "Deliberately duplicating or combining data to make common reads faster or simpler.",
    "determinism": "The property that the same inputs and relevant state always produce the same result.",
    "etl": "Extract, transform, load: moving data from sources through transformations into a destination.",
    "eventual consistency": "A model where replicas may temporarily differ but converge if writes stop.",
    "idempotency": "The property that repeating an operation has the same intended effect as doing it once.",
    "latency": "The elapsed time between starting an operation and receiving its result.",
    "normalization": "Structuring relational data to reduce duplication and improve integrity.",
    "orchestration": "Coordinating the order, dependencies, retries, and monitoring of computational work.",
    "parallelism": "Performing multiple computations simultaneously using separate execution resources.",
    "partition": "A division of data into independent subsets, often for storage, processing, or pruning.",
    "pipeline": "A sequence of automated processing steps that turns inputs into a defined output.",
    "replica": "A maintained copy of data, usually used for availability, scale, or disaster recovery.",
    "runtime": "The environment and period in which a program is executing.",
    "schema": "The formal structure, fields, types, and relationships expected in a data set or database.",
    "shard": "A horizontally partitioned subset of a larger data set distributed across storage or compute nodes.",
    "sql": "A language for defining, querying, and modifying data in relational database systems.",
    "throughput": "The amount of work or data a system completes in a unit of time.",
    "transaction": "A group of operations treated as one logical unit of work.",
}


@dataclass(frozen=True)
class Definition:
    """One concise definition and the source that supplied it."""

    term: str
    definition: str
    source: str


def lookup_definition(term: str) -> Definition | None:
    """Return a tech-first local definition, then use the no-key online fallback."""
    normalized = _normalize_term(term)
    if not normalized:
        return None
    if normalized in TECH_DEFINITIONS:
        return Definition(term=normalized, definition=TECH_DEFINITIONS[normalized], source="technology")
    local_definition = _local_definitions().get(normalized)
    if local_definition is not None:
        return Definition(term=normalized, definition=local_definition, source="local dictionary")
    cached_definition = _cached_definitions().get(normalized)
    if cached_definition is not None:
        return Definition(term=normalized, definition=cached_definition, source="cached dictionary")
    remote_definition = _fetch_remote_definition(normalized)
    if remote_definition is None:
        return None
    _save_cached_definition(normalized, remote_definition)
    return Definition(term=normalized, definition=remote_definition, source="online dictionary")


def _normalize_term(term: str) -> str:
    """Normalize user input without altering meaningful internal spaces or punctuation."""
    return " ".join(term.strip().casefold().split())


@cache
def _local_definitions() -> dict[str, str]:
    """Load the compressed built-in glossary only when a lookup requires it."""
    glossary_path = files("df").joinpath("assets", "glossary.json.gz")
    with glossary_path.open("rb") as compressed_file:
        with gzip.open(compressed_file, "rt", encoding="utf-8") as glossary_file:
            loaded = json.load(glossary_file)
    return {term: definition for term, definition in loaded.items() if isinstance(term, str) and isinstance(definition, str)}


@cache
def _cached_definitions() -> dict[str, str]:
    """Load prior online lookups from the per-user cache when present."""
    cache_path = _cache_path()
    if not cache_path.is_file():
        return {}
    try:
        loaded = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {term: definition for term, definition in loaded.items() if isinstance(term, str) and isinstance(definition, str)}


def _save_cached_definition(term: str, definition: str) -> None:
    """Persist a successful online lookup without making cache failure fatal."""
    cached_definitions = _cached_definitions()
    cached_definitions[term] = definition
    cache_path = _cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cached_definitions, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except OSError:
        return


@cache
def _cache_path() -> Path:
    """Return the user-local cache location without writing during import."""
    return Path.home() / ".cache" / "df" / "definitions.json"


def _fetch_remote_definition(term: str) -> str | None:
    """Request one fallback definition from Free Dictionary API without credentials."""
    request = Request(
        f"{DICTIONARY_API_URL}{quote(term)}",
        headers={"Accept": "application/json", "User-Agent": "df-definition-finder/0.1"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        meanings = entry.get("meanings")
        if not isinstance(meanings, list):
            continue
        for meaning in meanings:
            if not isinstance(meaning, dict):
                continue
            definitions = meaning.get("definitions")
            if not isinstance(definitions, list) or not definitions:
                continue
            first_definition = definitions[0]
            if isinstance(first_definition, dict) and isinstance(first_definition.get("definition"), str):
                return first_definition["definition"]
    return None
