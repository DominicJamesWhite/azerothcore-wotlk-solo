/*
 * tooltip.js - the hover card.
 *
 * Shows the description for the rank you currently have, plus a dimmed
 * preview of the next rank when the talent is partially spent.  That mirrors
 * the in-game talent frame, and it is the detail that makes the calculator
 * usable for planning rather than just looking at.
 */

import { prereqOf, POINTS_PER_TIER, pointsInTree } from './talents.js';

const el = document.getElementById('tooltip');
let showRaw = false;

export function setShowRaw(value) {
  showRaw = value;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Mark the tokens the exporter could not resolve so they read as markup
 * rather than as prose.  We do it here, from the `unresolved` list, so the
 * JSON stays plain text.
 */
function renderDescription(rank) {
  const text = showRaw && rank.raw ? rank.raw : rank.desc;
  let html = escapeHtml(text);
  if (!showRaw && rank.unresolved) {
    for (const token of rank.unresolved) {
      const escaped = escapeHtml(token);
      html = html.split(escaped).join(`<span class="unresolved">${escaped}</span>`);
    }
  }
  return html;
}

const KIND_LABEL = {
  new: 'New talent',
  structure: 'Moved or restructured',
  renamed: 'Renamed',
  values: 'Values changed',
  description: 'Description changed',
};

export function show(anchor, { classData, tree, talent, state }) {
  const points = state[talent.id] || 0;
  const current = talent.ranks[Math.max(0, points - 1)];
  const next = points > 0 && points < talent.maxPoints ? talent.ranks[points] : null;

  const parts = [];
  parts.push(`<h3>${escapeHtml(talent.name)}</h3>`);
  parts.push(`<p class="rank">Rank ${points} / ${talent.maxPoints}</p>`);

  if (talent.modified) {
    const label = KIND_LABEL[talent.modKind] || 'Modified';
    const was = talent.baseName
      ? ` &mdash; was &ldquo;${escapeHtml(talent.baseName)}&rdquo;`
      : '';
    parts.push(`<p class="badge-line">Alonecraft: ${label}${was}</p>`);
  }

  if (current) {
    parts.push(`<p class="desc">${renderDescription(current)}</p>`);
  }
  if (next) {
    parts.push(`<p class="next-label">Next rank:</p>`);
    parts.push(`<p class="desc next">${renderDescription(next)}</p>`);
  }

  // Why a talent is locked is the question players actually have, so answer
  // it explicitly rather than just greying the cell out.
  const reasons = [];
  const required = talent.location.rowIdx * POINTS_PER_TIER;
  const spent = pointsInTree(tree, state);
  if (spent < required) {
    reasons.push(`Requires ${required} points in ${escapeHtml(tree.name)} (you have ${spent})`);
  }
  const prereq = prereqOf(tree, talent);
  if (prereq) {
    const needed = talent.prereqRank || prereq.maxPoints;
    if ((state[prereq.id] || 0) < needed) {
      reasons.push(`Requires ${needed} point(s) in ${escapeHtml(prereq.name)}`);
    }
  }
  if (reasons.length) {
    parts.push(`<p class="requires">${reasons.join('<br>')}</p>`);
  }

  const spellId = (current || talent.ranks[0] || {}).spell;
  if (spellId) {
    parts.push(`<p class="spellid">spell ${spellId}</p>`);
  }

  el.innerHTML = parts.join('');
  el.hidden = false;

  const rect = anchor.getBoundingClientRect();
  const width = el.offsetWidth;
  let left = rect.right + 12;
  if (left + width > window.innerWidth - 8) left = rect.left - width - 12;
  if (left < 8) left = 8;
  let top = rect.top + window.scrollY;
  const maxTop = window.scrollY + window.innerHeight - el.offsetHeight - 8;
  if (top > maxTop) top = Math.max(window.scrollY + 8, maxTop);
  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
}

export function hide() {
  el.hidden = true;
}
