# Alonecraft Account Portal

A small LAN-only web page where players register an account and change their own
password or email, instead of a GM running `.account create` for each of them.

```bash
tools\run_portal.bat                          # LAN, port 8090
python tools/portal/server.py                 # 127.0.0.1 only
python tools/portal/server.py --host 0.0.0.0 --port 8090
```

Ctrl-C in its console stops it. It is **not** started or stopped by
`build_and_run.bat` / `tools/stop_server.ps1` — those manage
`worldserver.exe` / `authserver.exe` only.

## What it does

| Endpoint | Requires |
|----------|----------|
| `POST /api/register` | username, password, optional email |
| `POST /api/change-password` | username, current password, new password |
| `POST /api/change-email` | username, password, new email |

Both change operations verify the current password by recomputing the SRP6
verifier from the account's stored salt — the same check `SRP6::CheckLogin` does.

Account deletion is deliberately **not** exposed. `AccountMgr::DeleteAccount`
kicks online players and deletes every character through `Player::DeleteFromDB`,
which touches mail, guilds, arena teams, auctions and item instances across
`acore_characters`. Reimplementing that in Python would leave orphan rows. Use
`.account delete <name>` from the worldserver console.

## How it works

It writes `acore_auth.account` rows directly, mirroring
`AccountMgr::CreateAccount` (`src/server/game/Accounts/AccountMgr.cpp:43`):
same length limits (username ≤ 17, password ≤ 16, email ≤ 255), same
uppercasing of username/password/email, the same `LOGIN_INS_ACCOUNT` column set,
and the same `LOGIN_INS_REALM_CHARACTERS_INIT` follow-up.

SOAP was the alternative and cannot express "change my password, proving I know
the old one" — `.account set password` is a GM operation that never checks the
caller's existing password. It would also mean an admin credential in a config
file and a hard dependency on worldserver uptime.

`srp6.py` is a port of `src/common/Cryptography/Authentication/SRP6.cpp`. Every
big-integer↔bytes conversion in it is little-endian, because `BigNumber`'s array
constructor and `ToByteArray` both default to `littleEndian = true`
(`src/common/Cryptography/BigNumber.h:38,123`). Getting any of that wrong fails
*silently*: the account is created and the client just says the password is
wrong. That is what `test_srp6.py` exists to prevent.

## Tests

```bash
python tools/portal/test_srp6.py             # offline + live
python tools/portal/test_srp6.py --offline   # no database needed
```

The live check is the real proof. mod-playerbots creates its `RNDBOT*` accounts
with `password == account name` when `AiPlayerbot.RandomBotRandomPassword = 0`
(the deployed value), so those rows are known-plaintext vectors written by the
*compiled* `Acore::Crypto::SRP6`. Re-run this after any upstream sync — it is
the only thing that catches a KDF change.

## Passwords are not case sensitive

The 3.3.5a client uppercases the password before it is ever sent, so the server
derives its verifier from the uppercase form. `Hunter2` and `HUNTER2` are the
same password. The page says so; expect to be asked anyway.

## LAN players also need the realmlist address

`data/sql/base/db_auth/realmlist.sql:49` seeds `address` and `localAddress` as
`127.0.0.1`. A LAN player will authenticate fine and then be handed `127.0.0.1`
as the world server address — they connect to their own machine and appear to
hang at "Logging in to game server". The portal warns about this at startup and
after a successful registration.

To fix it, once, against the live database (**not** by editing the base SQL file
— that is upstream content applied to fresh databases and it will conflict on
every sync):

```sql
UPDATE realmlist SET address = '192.168.x.y' WHERE id = 1;  -- this host's LAN IPv4
-- leave localAddress = '127.0.0.1' so this machine still connects locally
```

Each player then sets `realmlist.wtf` in their WoW folder to
`set realmlist 192.168.x.y`.

## Styling

The page matches the talent calculator: same palette, same client fonts
(Morpheus headings, FrizQuadrata body), same frame idioms — the hairline gold
rule under the header, the double-inset bevel on panels, the left gutter every
band shares.

The rules are **copied** from `site/css/style.css`, not linked to it: that file
is written against talent-tree markup, `@font-face`s paths relative to
`site/assets/`, and is deployed to public GitHub Pages while this is LAN-only.
A calculator restyle must not be able to break the signup page.

The two TTFs are the exception — `server.py` serves them from
`site/assets/fonts/` at `/fonts/`, since they are 130 KB of binary already
extracted there. If they ever move, the CSS falls back to the declared system
stack and the page still reads fine.

## Notes

- Requires `mysql-connector-python`, already used by every tool in `tools/`. The server checks for it at startup rather than on the first form submit.
- Port 8090 avoids 3724 (auth), 8085 (world), 7878 (SOAP) and 3306 (MySQL).
- Windows Firewall prompts on the first `0.0.0.0` bind. Dismissing that dialog looks exactly like a broken service.
- One short-lived MySQL connection per request: `ThreadingHTTPServer` runs handlers concurrently and a connector connection is not thread-safe.
- In-memory rate limit of 10 requests/minute per IP.
- `expansion` is hardcoded to 2 (WotLK), matching the `account.expansion` column default. If `Expansion` in `worldserver.conf` ever changes, update `DEFAULT_EXPANSION` in `accounts.py`.
