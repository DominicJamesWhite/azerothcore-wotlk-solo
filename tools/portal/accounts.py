#!/usr/bin/env python3
"""
acore_auth account operations for the Alonecraft player portal.

Mirrors AccountMgr (src/server/game/Accounts/AccountMgr.cpp) rather than calling
it: the same validation limits, the same uppercasing, the same INSERT column set
as LOGIN_INS_ACCOUNT (src/server/database/Database/Implementation/LoginDatabase.cpp:82).

Connection details come from the DBC tooling's config.py, the same way every
other tool in tools/ does it (see verify_db.py:28-36) -- except that config.py
hardcodes MYSQL_DB to acore_world, so the auth database is named explicitly here.
"""

import os
import re
import sys

import srp6

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))

AUTH_DB = "acore_auth"

# CreateAccount rejects on `utf8length(x) > MAX_*` (AccountMgr.cpp:45-52), so
# these are the inclusive maxima the console's `.account create` accepts. Stay
# in lockstep with it -- an account the console cannot manage is an operator trap.
MAX_USERNAME_LEN = 17   # MAX_ACCOUNT_STR
MAX_PASSWORD_LEN = 16   # MAX_PASS_STR
MAX_EMAIL_LEN = 255
MIN_PASSWORD_LEN = 4

# The core does not enforce a username charset. The portal does, because a LAN
# signup form should not be where we discover what the client chokes on.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Matches the `expansion` column default and CONFIG_EXPANSION (2 = WotLK).
DEFAULT_EXPANSION = 2


class AccountError(Exception):
    """A user-facing validation or conflict error. The message is shown as-is."""


def get_db_connection():
    import config
    import mysql.connector
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASS,
        database=AUTH_DB,
    )


def _validate_username(username):
    username = (username or "").strip()
    if not username:
        raise AccountError("Username is required.")
    if len(username) > MAX_USERNAME_LEN:
        raise AccountError(f"Username must be at most {MAX_USERNAME_LEN} characters.")
    if not USERNAME_RE.match(username):
        raise AccountError("Username may only contain letters, numbers and underscores.")
    return srp6.normalize(username)


def _validate_password(password):
    password = password or ""
    if len(password) < MIN_PASSWORD_LEN:
        raise AccountError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    if len(password) > MAX_PASSWORD_LEN:
        raise AccountError(f"Password must be at most {MAX_PASSWORD_LEN} characters.")
    if not password.isascii():
        raise AccountError("Password must use ASCII characters only.")
    return password


def _validate_email(email, required=True):
    email = (email or "").strip()
    if not email:
        if required:
            raise AccountError("Email is required.")
        return ""
    if len(email) > MAX_EMAIL_LEN:
        raise AccountError(f"Email must be at most {MAX_EMAIL_LEN} characters.")
    if not EMAIL_RE.match(email):
        raise AccountError("That does not look like an email address.")
    # CreateAccount uppercases the email too (AccountMgr.cpp:56), and both
    # reg_mail and email get the same value.
    return srp6.normalize(email)


def get_account(conn, username):
    """Return (id, username, salt, verifier) or None."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, username, salt, verifier FROM account WHERE username = %s",
            (srp6.normalize(username),),
        )
        return cur.fetchone()
    finally:
        cur.close()


def _authenticate(conn, username, password):
    """Return the account id, or raise AccountError on bad credentials."""
    row = get_account(conn, username)
    if not row:
        raise AccountError("Username or password is incorrect.")
    account_id, name, salt, verifier = row
    if not srp6.check_login(name, password or "", bytes(salt), bytes(verifier)):
        raise AccountError("Username or password is incorrect.")
    return account_id


def create_account(conn, username, password, email):
    username = _validate_username(username)
    password = _validate_password(password)
    email = _validate_email(email, required=False)

    if get_account(conn, username):
        raise AccountError("That username is already taken.")

    salt, verifier = srp6.make_registration_data(username, password)

    assert len(salt) == 32 and len(verifier) == 32, "binary(32) columns pad and truncate silently"

    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO account (username, salt, verifier, expansion, reg_mail, email, joindate) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW())",
            (username, salt, verifier, DEFAULT_EXPANSION, email, email),
        )
        account_id = cur.lastrowid
        # CreateAccount runs LOGIN_INS_REALM_CHARACTERS_INIT straight after the
        # insert (AccountMgr.cpp:73-75). Without it the realm character count is
        # missing for the new account. Self-selecting, so it is idempotent.
        cur.execute(
            "INSERT INTO realmcharacters (realmid, acctid, numchars) "
            "SELECT realmlist.id, account.id, 0 FROM realmlist, account "
            "LEFT JOIN realmcharacters ON acctid = account.id WHERE acctid IS NULL"
        )
        conn.commit()
        return account_id
    except Exception as exc:
        conn.rollback()
        # The pre-check above is a race; the UNIQUE index on username is the
        # real guard, so translate its error rather than 500ing.
        if type(exc).__name__ == "IntegrityError":
            raise AccountError("That username is already taken.") from exc
        raise
    finally:
        cur.close()


def get_realm_address(conn):
    """The address the authserver hands clients for realm 1, or None."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT address FROM realmlist ORDER BY id LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


def change_password(conn, username, current_password, new_password):
    account_id = _authenticate(conn, username, current_password)
    new_password = _validate_password(new_password)

    # ChangePassword re-derives a fresh salt as well as the verifier
    # (AccountMgr.cpp:217), so the new salt must be written too.
    salt, verifier = srp6.make_registration_data(username, new_password)

    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE account SET salt = %s, verifier = %s WHERE id = %s",
            (salt, verifier, account_id),
        )
        # Not something ChangePassword does, but free and correct: drop the
        # cached session key so a live session cannot survive the change.
        cur.execute("UPDATE account SET session_key = NULL WHERE id = %s", (account_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def change_email(conn, username, current_password, new_email):
    account_id = _authenticate(conn, username, current_password)
    new_email = _validate_email(new_email, required=True)

    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE account SET email = %s WHERE id = %s",
            (new_email, account_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
