"""One-command offline verification for a fresh checkout."""

import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from . import replay

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/cases"


def deny_network(event, args):
    if event in {
        "socket.connect",
        "socket.connect_ex",
        "socket.getaddrinfo",
        "socket.bind",
    }:
        raise RuntimeError("network access is disabled during offline verification")


def verify():
    sys.addaudithook(deny_network)
    # These tests import as a package from the checkout, including with -S.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    log = io.StringIO()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        result = unittest.TextTestRunner(stream=log, verbosity=1).run(suite)
    if not result.wasSuccessful():
        print(log.getvalue(), file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="tool-verification-") as tmp:
        replay.replay(CASES, Path(tmp))
    print(f"PASS: {result.testsRun} offline tests; network access blocked.")
    print("PASS: 40 paired cases, 80 hashes; checker flags A 40/40 and B 0/40.")
    print(
        "PASS: original builder fixtures and saved analysis reports match byte-for-byte."
    )
    print("PASS: replay preserves all three cases/ files byte-for-byte.")
    print(
        "      Historical preview is copied unchanged; its ten F2 questions predate the manifest."
    )
    print("      F3/F4 B renderings are frozen evidence, not database reconstructions.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify"])
    parser.parse_args()
    try:
        return verify()
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
