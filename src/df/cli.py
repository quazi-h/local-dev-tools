"""Command-line entry point for Definition Finder."""

import sys

import cyclopts

from df.definitions import lookup_definition

app = cyclopts.App(name="df")


@app.default
def define(term: str) -> None:
    """Look up a word or short phrase, preferring technology meanings."""
    result = lookup_definition(term)
    if result is None:
        print(f"No definition found for: {term}", file=sys.stderr)
        raise SystemExit(1)
    print(f"{result.term} [{result.source}]")
    print(result.definition)
