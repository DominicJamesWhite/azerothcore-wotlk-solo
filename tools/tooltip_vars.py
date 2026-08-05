"""
tooltip_vars.py - Resolve WoW 3.3.5a tooltip variables in spell text.

Spell.dbc descriptions are templates, not prose:

    "Reduces the cast time of your Fireball by $s1 sec."

The client substitutes $-tokens at render time from the spell's own row.  A web
talent calculator has no client, so we resolve them at export time.

Design notes:

  * resolve() is pure.  It takes an already-loaded spell row and a bag of index
    tables; it does no file I/O.  That makes it testable without a 49 MB DBC.
  * Anything we cannot resolve is LEFT IN PLACE and reported, never stripped.
    "Increases damage by ." is a silent lie; "Increases damage by $AP." tells
    you the resolver has a gap.
  * $?s[..][..] branch selection and $g gender are CHOICES, not resolutions.
    We always take the first branch and the male form, and say so on the site.

Run `python tools/export_talents.py --report-tokens` for a census of which
tokens actually occur and how many resolved.
"""

import re

# ── Aux table bundle ───────────────────────────────────────────────────────


class AuxTables:
    """Index DBCs the resolver needs, plus the full spell index for $@ refs.

    Every field is optional.  A missing table degrades the tokens that depend
    on it to "unresolved" rather than crashing, so a fresh clone that has not
    extracted the index DBCs still produces a usable export.
    """

    def __init__(self, spells=None, durations=None, radii=None,
                 ranges=None, cast_times=None):
        self.spells = spells or {}
        self.durations = durations or {}
        self.radii = radii or {}
        self.ranges = ranges or {}
        self.cast_times = cast_times or {}

    def missing(self):
        out = []
        if not self.durations:
            out.append("$d")
        if not self.radii:
            out.append("$a")
        if not self.ranges:
            out.append("$A")
        if not self.cast_times:
            out.append("$t")
        return out


# ── Number formatting ──────────────────────────────────────────────────────


def _fmt(value):
    """Format a number the way the client does: no trailing .0, 2dp at most."""
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _fmt_duration(ms):
    """Render a millisecond duration as the client does ("12 sec", "1 min")."""
    if ms <= 0:
        return "0 sec"
    secs = ms / 1000.0
    if secs < 60:
        return f"{_fmt(secs)} sec"
    mins = secs / 60.0
    if mins < 60:
        return f"{_fmt(mins)} min"
    return f"{_fmt(mins / 60.0)} hour"


# ── Effect values ──────────────────────────────────────────────────────────


def signed_effect_value(row, index):
    """CalcValue for effect `index` (1-3), keeping its sign.

    CLAUDE.md: both $s and $m add 1 to BasePoints --
    CalcValue = BasePoints + max(1, DieSides).
    """
    base = row.get(f"EffectBasePoints{index}", 0) or 0
    sides = row.get(f"EffectDieSides{index}", 0) or 0
    return base + max(1, sides)


def effect_value(row, index):
    """CalcValue as printed in prose: magnitude only.

    A debuff stores a negative BasePoints but the client prints the magnitude
    -- "Reduces damage by 10%" is BasePoints -11.  Inside a ${...} expression
    the sign is load-bearing instead (Empowered Frostbolt's ${$m2/-1000}
    needs -100 / -1000 to reach 0.1), so expressions use the signed form.
    """
    return abs(signed_effect_value(row, index))


def _duration_ms(row, aux):
    entry = aux.durations.get(row.get("DurationIndex", 0) or 0)
    return entry["Duration"] if entry else None


# ── The resolver ───────────────────────────────────────────────────────────

# Ordered longest-first so that e.g. $@spelldesc wins over $@, and $/N; wins
# over a bare $s.  A single regex keeps one left-to-right pass, which matters
# because $l pluralisation depends on the previously emitted number.
_TOKEN = re.compile(
    r"""\$
    (?:
        (?P<div>/(?P<divn>[0-9.]+);)        # $/1000;s1
      | (?P<mul>\*(?P<muln>[0-9.]+);?)      # $*2;s1  and  $*2s1
    )?
    (?P<ref>\d+)?                           # $12536s1 -- effect of ANOTHER spell
    (?:
        (?P<atname>@spellname(?P<atnid>\d+))
      | (?P<atdesc>@spelldesc(?P<atdid>\d+))
      | (?P<eff>[smoxSMOX](?P<effn>[123]))
      | (?P<amp>[tT](?P<ampn>[123]))
      | (?P<radius>a(?P<radn>[123]))
      | (?P<rng>A(?P<rngn>[123]))
      | (?P<dur>[dD])(?![a-zA-Z])
      | (?P<proc>h)[123]?(?![a-zA-Z])       # $h and $h1 both mean ProcChance
      | (?P<stack>u)(?![a-zA-Z])
      | (?P<charges>n)(?![a-zA-Z])
      | (?P<cast>t)(?![a-zA-Z])
      | (?P<named><(?P<namedv>[^>]+)>)
    )
    """,
    re.VERBOSE,
)


def resolve(text, base_row, aux=None, _depth=0, _seen=None):
    """Resolve tooltip variables in `text` using spell `base_row`.

    Returns (resolved_text, unresolved_tokens).  `unresolved_tokens` lists the
    literal token strings left in place, for reporting and for styling on the
    site.
    """
    if not text:
        return text or "", []

    aux = aux or AuxTables()
    _seen = _seen or set()
    unresolved = []
    # $l pluralises against the most recently emitted number, mirroring the
    # client's own single-pass renderer.
    state = {"last": None}

    def emit_number(value):
        state["last"] = value
        return _fmt(value)

    def sub(m):
        tok = m.group(0)

        # --- $12536s1: read the effect off a DIFFERENT spell's row ---------
        row = base_row
        if m.group("ref"):
            row = aux.spells.get(int(m.group("ref")))
            if row is None:
                unresolved.append(tok)
                return tok

        # --- scaling prefixes, applied to whatever value the token yields ---
        scale = 1.0
        if m.group("div"):
            try:
                scale /= float(m.group("divn"))
            except (TypeError, ValueError):
                pass
        if m.group("mul"):
            try:
                scale *= float(m.group("muln"))
            except (TypeError, ValueError):
                pass

        # --- $s1 $m1 $o1 $x1 --------------------------------------------
        if m.group("eff"):
            kind = m.group("eff")[0].lower()
            n = int(m.group("effn"))
            if kind in ("s", "m"):
                return emit_number(effect_value(row, n) * scale)
            if kind == "x":
                return emit_number((row.get(f"EffectChainTarget{n}", 0) or 0) * scale)
            if kind == "o":
                # total-over-time = per-tick value * number of ticks
                amp = row.get(f"EffectAmplitude{n}", 0) or 0
                dur = _duration_ms(row, aux)
                if dur is None or amp <= 0:
                    unresolved.append(tok)
                    return tok
                ticks = max(1, int(round(dur / amp)))
                return emit_number(effect_value(row, n) * ticks * scale)

        # --- $t1 periodic amplitude, in seconds --------------------------
        if m.group("amp"):
            n = int(m.group("ampn"))
            amp = row.get(f"EffectAmplitude{n}", 0) or 0
            if amp <= 0:
                unresolved.append(tok)
                return tok
            return emit_number(amp / 1000.0 * scale)

        # --- $d duration --------------------------------------------------
        if m.group("dur"):
            dur = _duration_ms(row, aux)
            if dur is None:
                unresolved.append(tok)
                return tok
            state["last"] = dur / 1000.0
            if scale != 1.0:
                return emit_number(dur / 1000.0 * scale)
            return _fmt_duration(dur)

        # --- $t bare: cast time -------------------------------------------
        if m.group("cast"):
            entry = aux.cast_times.get(row.get("CastingTimeIndex", 0) or 0)
            if not entry:
                unresolved.append(tok)
                return tok
            return emit_number(entry["CastTime"] / 1000.0 * scale)

        # --- $a1 radius / $A1 range ---------------------------------------
        if m.group("radius"):
            n = int(m.group("radn"))
            entry = aux.radii.get(row.get(f"EffectRadiusIndex{n}", 0) or 0)
            if not entry:
                unresolved.append(tok)
                return tok
            return emit_number(entry["Radius"] * scale)

        if m.group("rng"):
            entry = aux.ranges.get(row.get("RangeIndex", 0) or 0)
            if not entry:
                unresolved.append(tok)
                return tok
            return emit_number(entry["MaxRangeHostile"] * scale)

        # --- simple row fields --------------------------------------------
        if m.group("proc"):
            return emit_number((row.get("ProcChance", 0) or 0) * scale)
        if m.group("stack"):
            return emit_number((row.get("StackAmount", 0) or 0) * scale)
        if m.group("charges"):
            return emit_number((row.get("ProcCharges", 0) or 0) * scale)

        # --- $@spellname123 / $@spelldesc123 ------------------------------
        if m.group("atname"):
            other = aux.spells.get(int(m.group("atnid")))
            if not other:
                unresolved.append(tok)
                return tok
            return other.get("SpellName0", "") or tok

        if m.group("atdesc"):
            sid = int(m.group("atdid"))
            other = aux.spells.get(sid)
            if not other or _depth >= 3 or sid in _seen:
                unresolved.append(tok)
                return tok
            inner, inner_unres = resolve(
                other.get("SpellDescription0", ""), other, aux,
                _depth + 1, _seen | {sid},
            )
            unresolved.extend(inner_unres)
            return inner

        # --- $<var> named variable ----------------------------------------
        if m.group("named"):
            unresolved.append(tok)
            return tok

        unresolved.append(tok)
        return tok

    # Order matters: conditionals first (they contain tokens), then ${...}
    # expressions (they contain $-variables), then plain tokens, then the
    # text-selection tokens that depend on the last emitted number.
    text = _resolve_conditionals(text, base_row, aux)
    text, expr_unres = _resolve_expressions(text, base_row, aux)
    unresolved.extend(expr_unres)
    out = _TOKEN.sub(sub, text)
    out = _resolve_plurals(out, state)
    out = _resolve_gender(out)
    return out, unresolved


# ── ${...} arithmetic ──────────────────────────────────────────────────────
# e.g. ${$m2/-1000}.1  ->  0.1        ${110*1.45}%  ->  160%
#
# Variables that depend on the character (attack power, spell power, weapon
# damage) are deliberately NOT substituted: there is no correct value without
# a player, and inventing one produces a confident lie.  Any expression that
# mentions one is left raw in full.

_EXPR = re.compile(r"\$\{(?P<body>[^{}]*)\}(?:\.(?P<prec>\d+))?")

# $AP $RAP $SP $SPH ... and the $mw/$MW weapon-damage pair.
_CHAR_VAR = re.compile(r"\$(?:AP|RAP|SPH?|SP[A-Z]*|[mM][wW]|PL)\b")


class _ExprError(Exception):
    pass


def _expr_vars(body, row, aux):
    """Substitute $-variables inside an expression body with their numbers."""
    def var(m):
        ref, kind, idx = m.group("ref"), m.group("kind"), m.group("idx")
        src = row
        if ref:
            src = aux.spells.get(int(ref))
            if src is None:
                raise _ExprError(f"unknown spell {ref}")
        if idx is None:
            # Scalar row fields: ${$h/2} (Missile Barrage) and friends.
            if kind == "h":
                value = src.get("ProcChance", 0) or 0
            elif kind == "u":
                value = src.get("StackAmount", 0) or 0
            elif kind == "n":
                value = src.get("ProcCharges", 0) or 0
            else:
                raise _ExprError(f"unsupported var {m.group(0)}")
        elif kind in ("s", "m", "S", "M"):
            # $M1 is strictly the max roll and $m1 the min, but talents have
            # DieSides <= 1 so the two coincide -- and CLAUDE.md's +1 rule
            # already folds DieSides in.
            value = signed_effect_value(src, int(idx))
        elif kind in ("t", "T"):
            value = (src.get(f"EffectAmplitude{idx}", 0) or 0) / 1000.0
        else:
            raise _ExprError(f"unsupported var {m.group(0)}")
        # Parenthesise negatives so "a/$m2" does not become "a/-100" -> fine,
        # but "a-$m2" would silently become "a--100".  Positives stay bare so
        # a kept-raw expression reads naturally.
        return f"({value})" if value < 0 else _fmt(value)

    return re.sub(
        r"\$(?P<ref>\d+)?(?:(?P<kind>[smtSMT])(?P<idx>[123])"
        r"|(?P<kind2>[hun])(?![a-zA-Z0-9]))",
        lambda m: var(_ExprVar(m)), body,
    )


class _ExprVar:
    """Adapter so `var` can read either alternative of the regex uniformly."""

    def __init__(self, m):
        self._m = m
        self._kind = m.group("kind") or m.group("kind2")

    def group(self, name):
        if name == "kind":
            return self._kind
        if name == "idx":
            return self._m.group("idx")
        return self._m.group(name)


# Recursive-descent over + - * / and parentheses.  Deliberately not eval():
# this text comes from a data file and must never be executed.
_NUM = re.compile(r"\s*(\d+(?:\.\d+)?)")


def _eval_expr(s):
    pos = 0

    def peek():
        nonlocal pos
        while pos < len(s) and s[pos] == " ":
            pos += 1
        return s[pos] if pos < len(s) else ""

    def factor():
        nonlocal pos
        c = peek()
        if c == "(":
            pos += 1
            v = expr()
            if peek() != ")":
                raise _ExprError("unbalanced (")
            pos += 1
            return v
        if c == "-":
            pos += 1
            return -factor()
        if c == "+":
            pos += 1
            return factor()
        m = _NUM.match(s, pos)
        if not m:
            raise _ExprError(f"expected number at {pos!r}")
        pos = m.end()
        return float(m.group(1))

    def term():
        nonlocal pos
        v = factor()
        while True:
            c = peek()
            if c == "*":
                pos += 1
                v *= factor()
            elif c == "/":
                pos += 1
                d = factor()
                if d == 0:
                    raise _ExprError("division by zero")
                v /= d
            else:
                return v

    def expr():
        nonlocal pos
        v = term()
        while True:
            c = peek()
            if c == "+":
                pos += 1
                v += term()
            elif c == "-":
                pos += 1
                v -= term()
            else:
                return v

    value = expr()
    if peek():
        raise _ExprError(f"trailing input at {pos}")
    return value


def _resolve_expressions(text, row, aux):
    unresolved = []

    def keep_raw(body):
        """Give up on an expression, but still inline what we do know.

        "${38/100*$AP}" reads better than "${$m3/100*$AP}", and -- because the
        later token pass would have substituted $m3 anyway -- doing it here is
        what keeps the recorded `unresolved` string identical to the text the
        site has to highlight.
        """
        try:
            body = _expr_vars(body, row, aux)
        except _ExprError:
            pass
        raw = "${" + body + "}"
        unresolved.append(raw)
        return raw

    def one(m):
        body = m.group("body")
        if _CHAR_VAR.search(body):
            return keep_raw(body)
        try:
            value = _eval_expr(_expr_vars(body, row, aux))
        except (_ExprError, ValueError, ZeroDivisionError):
            return keep_raw(body)
        prec = m.group("prec")
        if prec is not None:
            return f"{value:.{int(prec)}f}"
        return _fmt(round(value))

    return _EXPR.sub(one, text), unresolved


# ── Bracket-structured tokens ──────────────────────────────────────────────
# $?s12345[A][B] cannot be a regex: A and B may themselves contain brackets.


def _scan_bracket(text, start):
    """Return (contents, index_after) for a [...] group starting at `start`."""
    if start >= len(text) or text[start] != "[":
        return None, start
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    return None, start


_COND_HEAD = re.compile(r"\$\?[sa]?\d*(?:[,&|]\d+)*")


def _resolve_conditionals(text, row, aux):
    """Collapse $?s<id>[A][B] to A -- the "you have it" branch.

    Always taking A is a deliberate choice, not a resolution: whether a player
    knows a spell is unknowable statically, and A is the informative branch.
    """
    out = []
    i = 0
    while i < len(text):
        m = _COND_HEAD.match(text, i)
        if not m:
            out.append(text[i])
            i += 1
            continue
        first, after = _scan_bracket(text, m.end())
        if first is None:
            out.append(text[i])
            i += 1
            continue
        second, after2 = _scan_bracket(text, after)
        out.append(first)
        i = after2 if second is not None else after
    return "".join(out)


_PLURAL = re.compile(r"\$l([^:;]*):([^;]*);")


def _resolve_plurals(text, state):
    """$lsecond:seconds; -- pick by the last emitted number."""
    def pick(m):
        singular, plural = m.group(1), m.group(2)
        n = state.get("last")
        if n is None:
            return plural
        return singular if abs(n - 1) < 1e-9 else plural
    return _PLURAL.sub(pick, text)


_GENDER = re.compile(r"\$[gG]([^:;]*):([^;]*);")


def _resolve_gender(text):
    """$ghe:she; -- always male; player gender is unknowable statically."""
    return _GENDER.sub(lambda m: m.group(1), text)


# ── Token census ───────────────────────────────────────────────────────────

_ANY_TOKEN = re.compile(r"\$[a-zA-Z@?/*<{][^\s,.;:!)\]]{0,14}")


def census(text):
    """Normalised token patterns in `text`, for --report-tokens."""
    return [re.sub(r"\d+", "#", t) for t in _ANY_TOKEN.findall(text or "")]
