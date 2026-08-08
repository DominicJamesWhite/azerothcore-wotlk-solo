#!/usr/bin/env python3
"""
SRP6 registration data, reimplemented in pure Python.

This is a faithful port of Acore::Crypto::SRP6
(src/common/Cryptography/Authentication/SRP6.cpp) so that an external tool can
create and re-key `acore_auth.account` rows without going through the server.

Every conversion between a big integer and bytes in AzerothCore's SRP6 is
LITTLE-ENDIAN: BigNumber's array constructor and ToByteArray both default to
littleEndian = true (src/common/Cryptography/BigNumber.h:38,123).

Getting any of this wrong fails silently -- the account row is created, the
account exists, and the client simply reports an incorrect password. See
test_srp6.py, which cross-checks against a row the C++ code wrote.
"""

import hashlib
import hmac
import os

# SRP6.cpp:26-27. N is stored there as a byte array built from this hex string
# with reverse=true, then read back as a little-endian BigNumber -- which round
# trips to exactly this value.
G = 7
N = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)

SALT_LENGTH = 32
VERIFIER_LENGTH = 32


def normalize(text):
    """Uppercase the way the server does before deriving a verifier.

    AccountMgr::CreateAccount runs Utf8ToUpperOnlyLatin over the username AND
    the password (AccountMgr.cpp:50-56) before handing them to SRP6, and
    SRP6.h:43 documents that as a precondition. WoW passwords are therefore
    case-insensitive.
    """
    return text.upper()


def calculate_verifier(username, password, salt):
    """v = g ^ H(s || H(U || ':' || P)) mod N   (SRP6.cpp:39-48)

    username and password must already be normalized().
    """
    h1 = hashlib.sha1(f"{username}:{password}".encode("utf-8")).digest()
    h2 = hashlib.sha1(salt + h1).digest()
    x = int.from_bytes(h2, "little")
    return pow(G, x, N).to_bytes(VERIFIER_LENGTH, "little")


def make_registration_data(username, password):
    """Return (salt, verifier) for a new or re-keyed account."""
    username = normalize(username)
    password = normalize(password)
    salt = os.urandom(SALT_LENGTH)
    return salt, calculate_verifier(username, password, salt)


def check_login(username, password, salt, verifier):
    """True if `password` is the account's password, given its stored salt."""
    if len(salt) != SALT_LENGTH or len(verifier) != VERIFIER_LENGTH:
        return False
    candidate = calculate_verifier(normalize(username), normalize(password), salt)
    return hmac.compare_digest(candidate, verifier)
