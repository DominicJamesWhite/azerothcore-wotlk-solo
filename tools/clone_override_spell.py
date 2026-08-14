#!/usr/bin/env python3
"""Clone a spell row that exists only in `alonecraft_spell_dbc`.

`gen_sql.py dbc --base` reads the binary Spell.dbc, so it cannot clone a
previously-created custom spell -- those rows live only in the override table
and in the .sql files that populate it.  This reads the row straight out of the
generated SQL, rewrites the columns you name, and emits a fresh idempotent
DELETE/INSERT pair.

    python tools/clone_override_spell.py --from-file <sql> --base 200745 \
        --new-id 200759 --set SpellName0="Focused Aim" --append-to <sql>
"""

import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..',
                                'modules', 'world_of_alonecraft', 'dbc'))
from spell_dbc import SPELL_COLUMNS  # noqa: E402

SQL_DIR = os.path.join(os.path.dirname(__file__), '..', 'modules',
                       'world_of_alonecraft', 'data', 'sql', 'db-world')


def split_values(text):
    """Split a SQL VALUES tuple body on top-level commas.

    Quotes are single-quoted with '' escaping, which is what the generator
    emits; nothing here nests parentheses.
    """
    out, buf, in_str, i = [], [], False, 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    buf.append("''")
                    i += 2
                    continue
                in_str = False
            buf.append(ch)
        elif ch == "'":
            in_str = True
            buf.append(ch)
        elif ch == ',':
            out.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    out.append(''.join(buf).strip())
    return out


def find_row(path, spell_id):
    text = io.open(path, encoding='utf-8').read()
    pattern = re.compile(r'^\((%d,.*?)\);\s*$' % spell_id, re.M | re.S)
    match = pattern.search(text)
    if not match:
        raise SystemExit('ERROR: no INSERT row for %d in %s' % (spell_id, path))
    values = split_values(match.group(1))
    if len(values) != len(SPELL_COLUMNS):
        raise SystemExit('ERROR: parsed %d columns, expected %d'
                         % (len(values), len(SPELL_COLUMNS)))
    return values


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from-file', required=True)
    ap.add_argument('--base', type=int, required=True)
    ap.add_argument('--new-id', type=int, required=True)
    ap.add_argument('--set', action='append', default=[], metavar='COL=VAL')
    ap.add_argument('--append-to', required=True)
    ap.add_argument('--comment', default='')
    args = ap.parse_args()

    src = args.from_file
    if not os.path.isabs(src) and not os.path.exists(src):
        src = os.path.join(SQL_DIR, src)

    values = find_row(src, args.base)
    index = {name: i for i, name in enumerate(SPELL_COLUMNS)}

    values[0] = str(args.new_id)
    changes = []
    for assignment in args.set:
        col, _, raw = assignment.partition('=')
        if col not in index:
            raise SystemExit('ERROR: unknown column %r' % col)
        pos = index[col]
        old = values[pos]
        # The original row tells us whether this column is a string, which is
        # more reliable than guessing from the replacement value.
        values[pos] = quote(raw) if old.startswith("'") else raw
        changes.append('%s: %s -> %s' % (col, old, values[pos]))

    dst = args.append_to
    if not os.path.isabs(dst):
        dst = os.path.join(SQL_DIR, dst)

    lines = ['']
    if args.comment:
        lines += ['-- ' + '=' * 60, '-- ' + args.comment, '-- ' + '=' * 60]
    lines.append('-- Cloned from %d by clone_override_spell.py' % args.base)
    for change in changes:
        lines.append('--   %s' % change)
    lines.append('')
    lines.append('DELETE FROM `alonecraft_spell_dbc` WHERE `ID` = %d;'
                 % args.new_id)
    lines.append('INSERT INTO `alonecraft_spell_dbc` (%s) VALUES'
                 % ', '.join('`%s`' % c for c in SPELL_COLUMNS))
    lines.append('(%s);' % ', '.join(values))
    lines.append('')

    with io.open(dst, 'a', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    print('Appended %d to %s' % (args.new_id, dst))


if __name__ == '__main__':
    main()
