"""CLI: convert cb_authenticate session JSON into curl ``-b`` cookie arguments."""

# Standard library

import argparse
import json
import pathlib
import shlex
import sys
import typing


def main(argv: typing.List[str] | None = None) -> int:
    """Read session JSON and print shell-safe ``curl`` cookie arguments (``-b`` ...)."""

    # Argument definitions

    p = argparse.ArgumentParser(
        description=(
            "Read JSON emitted by cb_authenticate (stdin or file) and print curl cookie arguments."
        ),
    )
    p.add_argument(
        "session_file",
        nargs="?",
        default="-",
        help="Path to session JSON; omit or '-' to read stdin.",
    )

    args = p.parse_args(argv)

    # Load raw JSON text

    if args.session_file == "-":
        raw = sys.stdin.read()
    else:
        raw = pathlib.Path(args.session_file).read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print("error: JSON root must be an object", file=sys.stderr)
        return 1

    cookie_header = data.get("cookie_header")

    if cookie_header is None:
        print("error: missing cookie_header (not cb_authenticate output?)", file=sys.stderr)
        return 1

    if not isinstance(cookie_header, str):
        print("error: cookie_header must be a string", file=sys.stderr)
        return 1

    # One ``-b`` / ``--cookie`` value matches curl's cookie-string semantics.

    print(shlex.join(["-b", cookie_header]))

    return 0
