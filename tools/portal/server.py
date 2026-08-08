#!/usr/bin/env python3
"""
Alonecraft player account portal.

A small LAN-only web service letting players register an account and change
their own password or email, without a GM running `.account create` for them.

    python tools/portal/server.py                    # 127.0.0.1:8090
    python tools/portal/server.py --host 0.0.0.0     # reachable on the LAN

This binds an UNAUTHENTICATED account-creation endpoint. It is meant for a
local network only -- do not port-forward it.
"""

import argparse
import json
import os
import socket
import sys
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import accounts

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")

# The client fonts the talent calculator uses. Served from site/assets/ rather
# than duplicated: they are 130 KB of binary, and the calculator is where they
# were extracted to. Missing files just fall back to the declared system stack.
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "site", "assets", "fonts")

# Explicit whitelist rather than SimpleHTTPRequestHandler's path translation --
# there is no directory to traverse if no path is ever derived from the request.
STATIC_ROUTES = {
    "/": (STATIC_DIR, "index.html", "text/html; charset=utf-8"),
    "/style.css": (STATIC_DIR, "style.css", "text/css; charset=utf-8"),
    "/portal.js": (STATIC_DIR, "portal.js", "text/javascript; charset=utf-8"),
    "/fonts/FRIZQT__.TTF": (FONT_DIR, "FRIZQT__.TTF", "font/ttf"),
    "/fonts/MORPHEUS.TTF": (FONT_DIR, "MORPHEUS.TTF", "font/ttf"),
}

MAX_BODY_BYTES = 8192
RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW = 60.0

_rate_history = defaultdict(deque)


def _rate_limited(client_ip):
    now = time.monotonic()
    history = _rate_history[client_ip]
    while history and now - history[0] > RATE_LIMIT_WINDOW:
        history.popleft()
    if len(history) >= RATE_LIMIT_REQUESTS:
        return True
    history.append(now)
    return False


class PortalHandler(BaseHTTPRequestHandler):
    server_version = "AlonecraftPortal/1.0"

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt, *args):
        # The default logs the full request line. Bodies never reach it, but
        # keep the format short and timestamped like the rest of our tooling.
        sys.stdout.write("[portal] %s %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()

    def _send(self, code, body, content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, payload):
        self._send(code, json.dumps(payload), "application/json; charset=utf-8")

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            raise accounts.AccountError("Malformed request.")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise accounts.AccountError("Malformed request.")
        if not isinstance(data, dict):
            raise accounts.AccountError("Malformed request.")
        return data

    # -- routes -----------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        route = STATIC_ROUTES.get(path)
        if not route:
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        directory, filename, content_type = route
        try:
            with open(os.path.join(directory, filename), "rb") as handle:
                self._send(200, handle.read(), content_type)
        except OSError:
            # A missing font is cosmetic (the CSS falls back to a system face);
            # a missing page is not. Either way, say which file.
            self.log_message("missing asset: %s", os.path.join(directory, filename))
            self._send(404, "Missing asset", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        handler = {
            "/api/register": self._register,
            "/api/change-password": self._change_password,
            "/api/change-email": self._change_email,
        }.get(path)
        if not handler:
            self._send_json(404, {"ok": False, "error": "Not found."})
            return

        if _rate_limited(self.client_address[0]):
            self._send_json(429, {"ok": False, "error": "Too many requests. Wait a minute."})
            return

        conn = None
        try:
            data = self._read_json()
            # One short-lived connection per request: ThreadingHTTPServer runs
            # handlers concurrently and a mysql.connector connection is not
            # thread-safe. At LAN volume the cost is irrelevant.
            conn = accounts.get_db_connection()
            result = handler(conn, data)
            self._send_json(200, {"ok": True, **(result or {})})
        except accounts.AccountError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self.log_message("error on %s: %s", path, exc)
            self._send_json(500, {"ok": False, "error": "Server error. Check the portal console."})
        finally:
            if conn is not None:
                conn.close()

    def _register(self, conn, data):
        accounts.create_account(
            conn, data.get("username"), data.get("password"), data.get("email")
        )
        self.log_message("registered %s", (data.get("username") or "?").upper())
        return {"realm_address": accounts.get_realm_address(conn)}

    def _change_password(self, conn, data):
        accounts.change_password(
            conn,
            data.get("username"),
            data.get("current_password"),
            data.get("new_password"),
        )
        self.log_message("password changed for %s", (data.get("username") or "?").upper())
        return None

    def _change_email(self, conn, data):
        accounts.change_email(
            conn, data.get("username"), data.get("password"), data.get("new_email")
        )
        self.log_message("email changed for %s", (data.get("username") or "?").upper())
        return None


def lan_ip():
    """Best guess at the LAN IPv4 this host is reachable on."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))  # no packets are sent
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def preflight():
    """Fail loudly at startup rather than on the first player's form submit."""
    try:
        import mysql.connector  # noqa: F401
    except ImportError:
        print("ERROR: mysql-connector-python is not installed for this interpreter.")
        print("       pip install mysql-connector-python")
        return None
    try:
        conn = accounts.get_db_connection()
    except Exception as exc:
        print(f"ERROR: cannot connect to {accounts.AUTH_DB}: {exc}")
        return None
    try:
        return accounts.get_realm_address(conn)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Alonecraft player account portal")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address; use 0.0.0.0 to allow LAN access (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    realm_address = preflight()
    if realm_address is None:
        return 1

    print("Alonecraft account portal")
    print(f"  local:  http://127.0.0.1:{args.port}/")
    if args.host == "0.0.0.0":
        print(f"  LAN:    http://{lan_ip()}:{args.port}/")
        print("  WARNING: account creation is unauthenticated. LAN only -- do not port-forward.")
    if realm_address in ("127.0.0.1", "localhost"):
        print(f"  WARNING: realmlist.address is {realm_address!r}, so LAN players will")
        print("           authenticate but fail to reach the world server. See README.md.")
    print("  Ctrl-C to stop.")

    server = ThreadingHTTPServer((args.host, args.port), PortalHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
