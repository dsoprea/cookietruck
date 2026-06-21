"""CLI: convert ct_authenticate session JSON into curl ``-b`` cookie arguments."""

# Standard library

import argparse
import json
import shlex
import sys


def main() -> int:
    """Read session JSON and print shell-safe ``curl`` cookie arguments (``-b`` ...)."""

    # Argument definitions

    p = argparse.ArgumentParser(
        prog="ct_to_curl",
        description=(
            "Read JSON emitted by ct_authenticate from stdin and print curl cookie arguments."
        ),
    )

    p.parse_args()

    raw = sys.stdin.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        message = "error: invalid JSON: {error}".format(error=error)
        print(message, file=sys.stderr)

        return 1

    if not isinstance(data, dict):
        print("error: JSON root must be an object", file=sys.stderr)

        return 1

    if "cookie_header" not in data:
        print("error: missing cookie_header (not ct_authenticate output?)", file=sys.stderr)

        return 1

    cookie_header = data["cookie_header"]

    if not isinstance(cookie_header, str):
        print("error: cookie_header must be a string", file=sys.stderr)
        return 1

    # One ``-b`` / ``--cookie`` value matches curl's cookie-string semantics.

    print(shlex.join(["-b", cookie_header]))

    return 0
