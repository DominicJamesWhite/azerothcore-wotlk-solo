/*
 * talents.js - talent point rules.
 *
 * Adapted from wowsims/wotlk (MIT) -- ui/core/talents/talents_picker.tsx --
 * reimplemented in plain JS and decoupled from its Player/proto types.
 * https://github.com/wowsims/wotlk
 *
 * Everything here is a pure function over (classData, state), where state is
 * a plain { [talentId]: points } object.  No DOM, so it can be reasoned about
 * and tested on its own.
 */

export const MAX_POINTS = 71;
export const POINTS_PER_TIER = 5;

export function treeOf(classData, talentId) {
  for (const tree of classData.trees) {
    if (tree.talents.some(t => t.id === talentId)) return tree;
  }
  return null;
}

export function pointsInTree(tree, state) {
  return tree.talents.reduce((sum, t) => sum + (state[t.id] || 0), 0);
}

export function totalPoints(classData, state) {
  return classData.trees.reduce((sum, tree) => sum + pointsInTree(tree, state), 0);
}

function talentAt(tree, location) {
  if (!location) return null;
  return tree.talents.find(t =>
    t.location.rowIdx === location.rowIdx &&
    t.location.colIdx === location.colIdx) || null;
}

export function prereqOf(tree, talent) {
  return talentAt(tree, talent.prereqLocation);
}

/** Is `talent`'s prerequisite satisfied in `state`? */
export function prereqMet(tree, talent, state) {
  const prereq = prereqOf(tree, talent);
  if (!prereq) return true;
  // prereqRank is the number of points the parent needs; it defaults to the
  // parent's maximum, which is how every 3.3.5a talent actually behaves.
  const needed = talent.prereqRank || prereq.maxPoints;
  return (state[prereq.id] || 0) >= needed;
}

export function tierUnlocked(tree, talent, state) {
  return pointsInTree(tree, state) >= talent.location.rowIdx * POINTS_PER_TIER;
}

export function canAdd(classData, tree, talent, state) {
  if (talent.placeholder) return false;
  if ((state[talent.id] || 0) >= talent.maxPoints) return false;
  if (totalPoints(classData, state) >= MAX_POINTS) return false;
  if (!tierUnlocked(tree, talent, state)) return false;
  return prereqMet(tree, talent, state);
}

/**
 * Removing a point is only legal if the resulting tree is still valid.
 *
 * We simulate the removal and re-validate the whole tree rather than tracking
 * dependencies incrementally: a tree has ~24 talents, so it costs nothing,
 * and it cannot drift out of sync with the add rules the way bookkeeping can.
 */
export function canRemove(classData, tree, talent, state) {
  if ((state[talent.id] || 0) <= 0) return false;
  const next = { ...state, [talent.id]: state[talent.id] - 1 };
  return isValidTree(tree, next);
}

export function isValidTree(tree, state) {
  const spent = pointsInTree(tree, state);
  for (const t of tree.talents) {
    const points = state[t.id] || 0;
    if (points === 0) continue;
    if (points > t.maxPoints) return false;
    if (spent < t.location.rowIdx * POINTS_PER_TIER) return false;
    if (!prereqMet(tree, t, state)) return false;
  }
  return true;
}

export function isValidBuild(classData, state) {
  if (totalPoints(classData, state) > MAX_POINTS) return false;
  return classData.trees.every(tree => isValidTree(tree, state));
}

export function addPoint(classData, tree, talent, state) {
  if (!canAdd(classData, tree, talent, state)) return state;
  return { ...state, [talent.id]: (state[talent.id] || 0) + 1 };
}

export function removePoint(classData, tree, talent, state) {
  if (!canRemove(classData, tree, talent, state)) return state;
  return { ...state, [talent.id]: state[talent.id] - 1 };
}

/** Shift-click: add as many points as the rules allow. */
export function maxOut(classData, tree, talent, state) {
  let next = state;
  while (canAdd(classData, tree, talent, next)) {
    next = addPoint(classData, tree, talent, next);
  }
  return next;
}

export function resetTree(tree, state) {
  const next = { ...state };
  for (const t of tree.talents) delete next[t.id];
  return next;
}

/** Visual state for a talent cell. */
export function statusOf(classData, tree, talent, state) {
  const points = state[talent.id] || 0;
  if (points >= talent.maxPoints && points > 0) return 'maxed';
  if (points > 0) return 'partial';
  return canAdd(classData, tree, talent, state) ? 'available' : 'locked';
}
