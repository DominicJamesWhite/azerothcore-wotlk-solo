#!/usr/bin/env python3
"""
Tests for the portal's SRP6 port.

    python tools/portal/test_srp6.py           # offline + live checks
    python tools/portal/test_srp6.py --offline # no database needed

The live check is the one that matters. mod-playerbots creates its random-bot
accounts with `password == account name` when AiPlayerbot.RandomBotRandomPassword
is 0 (RandomPlayerbotFactory.cpp:613-624), which is the deployed value -- so
every RNDBOT* row in acore_auth is a known-plaintext vector written by the real
compiled Acore::Crypto::SRP6. If our port diverges in endianness, padding or
casing, this fails.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import srp6

FAILURES = []


def check(name, condition):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}")
        FAILURES.append(name)


def test_offline():
    print("offline:")

    # Regression guard, not ground truth -- this value comes from our own
    # implementation, pinned so an accidental edit is caught. test_live() is
    # what establishes correctness against the C++ code.
    salt = bytes(range(32))
    check(
        "frozen vector for TEST/TEST",
        srp6.calculate_verifier("TEST", "TEST", salt).hex()
        == "a57079472ffeddf921a6477b3b340f3691625bb0f1313427f38742e6f128b614",
    )

    salt, verifier = srp6.make_registration_data("PLAYER", "hunter2")
    check("salt is 32 bytes", len(salt) == 32)
    check("verifier is 32 bytes", len(verifier) == 32)
    check("correct password accepted", srp6.check_login("PLAYER", "hunter2", salt, verifier))
    check("case-insensitive password accepted", srp6.check_login("player", "HUNTER2", salt, verifier))
    check("wrong password rejected", not srp6.check_login("PLAYER", "hunter3", salt, verifier))
    check("wrong username rejected", not srp6.check_login("PLAYE", "hunter2", salt, verifier))
    check(
        "different salt rejected",
        not srp6.check_login("PLAYER", "hunter2", bytes(32), verifier),
    )

    # Verifiers whose top bytes are zero must still be a full 32 bytes, or the
    # BINARY(32) column pads them and the stored value no longer matches.
    lengths = set()
    for i in range(200):
        _, v = srp6.make_registration_data(f"USER{i}", f"pass{i}")
        lengths.add(len(v))
    check("every verifier is exactly 32 bytes", lengths == {32})


def test_live():
    print("live (acore_auth):")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import accounts

    try:
        conn = accounts.get_db_connection()
    except Exception as exc:
        print(f"  SKIP  cannot connect to {accounts.AUTH_DB}: {exc}")
        return

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, salt, verifier FROM account "
            "WHERE username LIKE 'RNDBOT%' LIMIT 25"
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    if not rows:
        print("  SKIP  no RNDBOT* accounts found (playerbots not seeded?)")
        return

    bad = [
        name for name, salt, verifier in rows
        if not srp6.check_login(name, name, bytes(salt), bytes(verifier))
    ]
    check(f"{len(rows)} server-written rows verify against our port", not bad)
    if bad:
        print(f"        mismatched: {', '.join(bad[:5])}")


def main():
    parser = argparse.ArgumentParser(description="Test the portal's SRP6 port")
    parser.add_argument("--offline", action="store_true", help="skip the database check")
    args = parser.parse_args()

    test_offline()
    if not args.offline:
        test_live()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
