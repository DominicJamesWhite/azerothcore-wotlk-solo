/*
 * tree.js - render one talent tree: the 4-column grid, the icons, and the
 * prerequisite arrows.
 *
 * Arrow geometry follows wowsims/wotlk (MIT): three cases only -- same
 * column, same row, and the diagonal -- drawn as straight lines between cell
 * centres.  WoW's own frame does no orthogonal routing either.
 */

import {
  pointsInTree, statusOf, prereqOf, POINTS_PER_TIER,
} from './talents.js';

const COLS = 4;
export const CELL = 56;
export const GAP = 18;
// Inset so the frame art shows around the outermost talents.
export const PAD = 10;

function cellCentre(location) {
  return {
    x: location.colIdx * (CELL + GAP) + CELL / 2,
    y: location.rowIdx * (CELL + GAP) + CELL / 2,
  };
}

function maxRow(tree) {
  return tree.talents.reduce((m, t) => Math.max(m, t.location.rowIdx), 0);
}

export function renderTree(tree, ctx) {
  const { classData, state, iconBase, highlight, onlyModified } = ctx;

  const section = document.createElement('section');
  section.className = 'tree';

  const spent = pointsInTree(tree, state);
  const header = document.createElement('header');
  header.className = 'tree-header';
  header.innerHTML = `
    <h2>${tree.name}</h2>
    <span class="tree-points">${spent}</span>
    <button type="button" class="tree-reset" data-tab="${tree.tabId}">Reset</button>
  `;
  section.appendChild(header);

  const grid = document.createElement('div');
  grid.className = 'grid';
  const rows = maxRow(tree) + 1;
  // The grid is padded, so the drawable area is inset by PAD on every side.
  grid.style.width = `${COLS * CELL + (COLS - 1) * GAP + PAD * 2}px`;
  grid.style.height = `${rows * CELL + (rows - 1) * GAP + PAD * 2}px`;
  // Each tree's own TalentFrame art, named by TalentTab.dbc's BackgroundFile.
  // Resolved to an absolute URL first: a relative url() inside a custom
  // property is resolved against the stylesheet that substitutes it, so
  // './assets/...' would be looked up under /css/ and 404. Going through
  // document.baseURI also keeps this correct on GitHub Pages, which serves
  // the site from a /<repo>/ subpath rather than the domain root.
  if (tree.background) {
    const url = new URL(`assets/trees/${tree.background}.png`, document.baseURI).href;
    grid.style.setProperty('--tree-bg', `url("${url}")`);
  }

  grid.appendChild(renderArrows(tree, state, rows));

  for (const talent of tree.talents) {
    // Retail ships empty talent rows; their array slot has to stay so build
    // links keep working, but there is nothing to draw.
    if (talent.placeholder) continue;

    const points = talent.points = state[talent.id] || 0;
    const status = statusOf(classData, tree, talent, state);

    const cell = document.createElement('button');
    cell.type = 'button';
    cell.className = `talent status-${status}`;
    if (talent.modified && highlight) cell.classList.add('modified');
    if (onlyModified && !talent.modified) cell.classList.add('dimmed');
    // + PAD because an absolutely positioned child is placed against the
    // padding box, so the grid's own padding does not shift it.
    cell.style.left = `${talent.location.colIdx * (CELL + GAP) + PAD}px`;
    cell.style.top = `${talent.location.rowIdx * (CELL + GAP) + PAD}px`;
    cell.dataset.talentId = talent.id;
    cell.dataset.tabId = tree.tabId;
    cell.setAttribute('aria-label',
      `${talent.name}, rank ${points} of ${talent.maxPoints}`);

    const img = document.createElement('img');
    img.alt = '';
    img.loading = 'lazy';
    img.src = talent.icon ? `${iconBase}${talent.icon}.png` : './assets/icon-fallback.svg';
    img.addEventListener('error', () => {
      img.src = './assets/icon-fallback.svg';
    }, { once: true });
    cell.appendChild(img);

    const counter = document.createElement('span');
    counter.className = 'counter';
    counter.textContent = `${points}/${talent.maxPoints}`;
    cell.appendChild(counter);

    if (talent.modified && highlight) {
      const dot = document.createElement('span');
      dot.className = 'mod-dot';
      dot.title = 'Changed on Alonecraft';
      cell.appendChild(dot);
    }

    grid.appendChild(cell);
  }

  section.appendChild(grid);
  return section;
}

function renderArrows(tree, state, rows) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'arrows');
  svg.setAttribute('width', COLS * CELL + (COLS - 1) * GAP);
  svg.setAttribute('height', rows * CELL + (rows - 1) * GAP);

  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  defs.innerHTML = `
    <marker id="head-on" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-head on"/>
    </marker>
    <marker id="head-off" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-head off"/>
    </marker>`;
  svg.appendChild(defs);

  for (const talent of tree.talents) {
    const prereq = prereqOf(tree, talent);
    if (!prereq) continue;

    const from = cellCentre(prereq.location);
    const to = cellCentre(talent.location);
    const needed = talent.prereqRank || prereq.maxPoints;
    const satisfied = (state[prereq.id] || 0) >= needed;

    // Stop short of the target cell so the arrowhead sits outside the icon.
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.hypot(dx, dy) || 1;
    const inset = CELL / 2 + 4;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', from.x + (dx / length) * inset);
    line.setAttribute('y1', from.y + (dy / length) * inset);
    line.setAttribute('x2', to.x - (dx / length) * inset);
    line.setAttribute('y2', to.y - (dy / length) * inset);
    line.setAttribute('class', `arrow ${satisfied ? 'on' : 'off'}`);
    line.setAttribute('marker-end', satisfied ? 'url(#head-on)' : 'url(#head-off)');
    svg.appendChild(line);
  }

  return svg;
}

export { POINTS_PER_TIER };
