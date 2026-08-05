/*
 * link.js - build strings, in the same format as gen_sql.py's `talent-link`.
 *
 * One digit per talent, in each tree's (rowIdx, colIdx) order, trees joined
 * by '-'.  That ordering comes from _build_talent_tree() in tools/gen_sql.py
 * and is baked into the exported `i` field, so a string produced here decodes
 * identically on the command line:
 *
 *     python tools/gen_sql.py talent-link --class priest --link "<string>" --source live
 *
 * This ordering is a wire format.  If the talent array order ever changes,
 * every previously shared link silently decodes to a different build --
 * export_talents.py --validate asserts `i` matches array position for exactly
 * that reason.
 */

export function encode(classData, state) {
  return classData.trees
    .map(tree => tree.talents
      .map(t => String(state[t.id] || 0))
      .join('')
      .replace(/0+$/, ''))
    .join('-');
}

export function decode(classData, str) {
  const state = {};
  const parts = String(str || '').split('-');
  while (parts.length < classData.trees.length) parts.push('');

  classData.trees.forEach((tree, treeIdx) => {
    const digits = parts[treeIdx] || '';
    for (let i = 0; i < digits.length && i < tree.talents.length; i++) {
      const points = Number(digits[i]);
      if (!Number.isFinite(points) || points <= 0) continue;
      const talent = tree.talents[i];
      state[talent.id] = Math.min(points, talent.maxPoints);
    }
  });
  return state;
}

/** '#priest/05032031-235050032302152530000331351' */
export function readHash() {
  const raw = decodeURIComponent(location.hash.replace(/^#/, ''));
  if (!raw) return { classKey: null, build: '' };
  const slash = raw.indexOf('/');
  if (slash === -1) return { classKey: raw, build: '' };
  return { classKey: raw.slice(0, slash), build: raw.slice(slash + 1) };
}

export function writeHash(classKey, build) {
  const hash = `#${classKey}${build ? '/' + build : ''}`;
  // replaceState, not pushState: otherwise the back button becomes a
  // point-by-point undo log of the whole session.
  history.replaceState(null, '', hash);
}
