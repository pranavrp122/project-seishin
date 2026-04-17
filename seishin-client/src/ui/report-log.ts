import { ReportLogEntry, ClaudeInteraction } from '../types.ts';

let logContainer: HTMLDivElement | null = null;
const entries: ReportLogEntry[] = [];

export function renderReportLog(parent: HTMLElement): void {
  logContainer = document.createElement('div');
  logContainer.id = 'report-log-list';
  logContainer.className = 'report-log-list';
  parent.appendChild(logContainer);
  renderEntries();
}

export function addReportLogEntry(entry: ReportLogEntry): void {
  entries.unshift(entry); // newest first
  if (logContainer) renderEntries();
}

function renderEntries(): void {
  if (!logContainer) return;
  while (logContainer.firstChild) logContainer.removeChild(logContainer.firstChild);

  if (entries.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'report-log-empty';

    const icon = document.createElement('div');
    icon.className = 'report-log-empty-icon';
    icon.textContent = '◷';

    const heading = document.createElement('div');
    heading.className = 'report-log-empty-heading';
    heading.textContent = 'No reports yet';

    const hint = document.createElement('div');
    hint.className = 'report-log-empty-hint';
    hint.textContent = 'Ask for a report and it\'ll show up here with the SQL, dashboard, and Claude back-and-forth.';

    const example = document.createElement('div');
    example.className = 'report-log-empty-example';
    example.textContent = 'e.g. "how many orders did we have this year"';

    empty.append(icon, heading, hint, example);
    logContainer.appendChild(empty);
    return;
  }

  const header = document.createElement('div');
  header.className = 'report-log-header';
  header.textContent = `Session reports · ${entries.length}`;
  logContainer.appendChild(header);

  for (const entry of entries) logContainer.appendChild(buildEntryEl(entry));
}

function buildEntryEl(entry: ReportLogEntry): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'report-entry';

  // Header bar — click to expand
  const headerEl = document.createElement('div');
  headerEl.className = 'report-entry-header';
  const title = document.createElement('span');
  title.className = 'report-entry-title';
  title.textContent = entry.query || '(no query)';
  const meta = document.createElement('span');
  meta.className = 'report-entry-meta';
  meta.textContent = `${entry.rowCount} row${entry.rowCount !== 1 ? 's' : ''} · ${formatTime(entry.timestamp)}`;
  const chevron = document.createElement('span');
  chevron.className = 'report-entry-chevron';
  chevron.textContent = '▸';
  headerEl.append(title, meta, chevron);
  wrap.appendChild(headerEl);

  // Detail container — starts hidden
  const detail = document.createElement('div');
  detail.className = 'report-entry-detail';
  detail.style.display = 'none';

  // Tab bar inside the detail
  const tabDefs = [
    { id: 'dashboard',  label: 'Dashboard' },
    { id: 'raw',        label: 'Raw Data' },
    { id: 'sql',        label: 'SQL' },
    { id: 'responses',  label: 'Responses' },
  ];

  const tabBar = document.createElement('div');
  tabBar.className = 'entry-tab-bar';
  const tabButtons: HTMLButtonElement[] = [];
  const tabPanes: Record<string, HTMLElement> = {};

  for (const t of tabDefs) {
    const btn = document.createElement('button');
    btn.className = 'entry-tab-btn' + (t.id === 'dashboard' ? ' active' : '');
    btn.textContent = t.label;
    btn.dataset.tab = t.id;
    tabButtons.push(btn);
    tabBar.appendChild(btn);
  }
  detail.appendChild(tabBar);

  // Build tab panes
  tabPanes.dashboard = buildDashboardPane(entry.results, entry.query);
  tabPanes.raw       = buildRawPane(entry.results, entry.rowCount);
  tabPanes.sql       = buildSqlPane(entry.sql);
  tabPanes.responses = buildResponsesPane(entry.claudeInteractions, entry.summary);

  for (const t of tabDefs) {
    const pane = tabPanes[t.id];
    pane.classList.add('entry-tab-pane');
    if (t.id === 'dashboard') pane.classList.add('active');
    detail.appendChild(pane);
  }

  // Tab switching
  tabButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const target = btn.dataset.tab!;
      tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      Object.entries(tabPanes).forEach(([id, pane]) => {
        pane.classList.toggle('active', id === target);
      });
    });
  });

  wrap.appendChild(detail);

  // Expand/collapse on header click
  headerEl.addEventListener('click', () => {
    const open = detail.style.display !== 'none';
    detail.style.display = open ? 'none' : 'block';
    chevron.textContent = open ? '▸' : '▾';
    wrap.classList.toggle('open', !open);
  });

  return wrap;
}

// ── Tab panes ───────────────────────────────────────────────────────────────

type ColKind = 'id' | 'numeric' | 'datetime' | 'categorical';
interface ColProfile { name: string; kind: ColKind; }

function buildDashboardPane(rows: Record<string, unknown>[], query: string): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'widget-wrap';
  if (!rows || rows.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'pane-empty';
    empty.textContent = 'No data returned.';
    wrap.appendChild(empty);
    return wrap;
  }

  const profile = profileColumns(rows);
  const numeric = profile.filter(c => c.kind === 'numeric');
  const datetime = profile.filter(c => c.kind === 'datetime');
  const categorical = profile.filter(c => c.kind === 'categorical');

  // Dispatch by shape
  if (rows.length === 1 && numeric.length === 1) {
    wrap.appendChild(buildBigNumber(rows[0], numeric[0], query));
  } else if (rows.length === 1 && numeric.length > 1) {
    wrap.appendChild(buildMetricGrid(rows[0], numeric));
  } else if (rows.length > 1 && datetime.length >= 1 && numeric.length >= 1) {
    wrap.appendChild(buildLineChart(rows, datetime[0], numeric[0]));
  } else if (rows.length > 1 && categorical.length >= 1 && numeric.length >= 1) {
    wrap.appendChild(buildBarChart(rows, categorical[0], numeric[0]));
  } else {
    wrap.appendChild(buildStyledTable(rows));
  }
  return wrap;
}

function profileColumns(rows: Record<string, unknown>[]): ColProfile[] {
  return Object.keys(rows[0]).map(name => {
    const lname = name.toLowerCase();
    if (lname === 'id' || lname.endsWith('_id')) return { name, kind: 'id' as ColKind };
    const sample = rows.slice(0, 10).map(r => r[name]).filter(v => v !== null && v !== undefined);
    if (sample.length === 0) return { name, kind: 'categorical' as ColKind };
    if (sample.every(v => typeof v === 'number')) return { name, kind: 'numeric' as ColKind };
    if (sample.every(v => typeof v === 'string' && /^\d{4}-\d{2}/.test(v as string))) return { name, kind: 'datetime' as ColKind };
    return { name, kind: 'categorical' as ColKind };
  });
}

function humanize(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function fmtNum(v: unknown): string {
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v ?? '');
}

function buildBigNumber(row: Record<string, unknown>, col: ColProfile, query: string): HTMLElement {
  const card = document.createElement('div');
  card.className = 'widget-bignum';
  const value = document.createElement('div');
  value.className = 'widget-bignum-value';
  value.textContent = fmtNum(row[col.name]);
  const label = document.createElement('div');
  label.className = 'widget-bignum-label';
  label.textContent = query || humanize(col.name);
  card.append(value, label);
  return card;
}

function buildMetricGrid(row: Record<string, unknown>, cols: ColProfile[]): HTMLElement {
  const grid = document.createElement('div');
  grid.className = 'widget-metric-grid';
  for (const c of cols) {
    const card = document.createElement('div');
    card.className = 'widget-metric-card';
    const v = document.createElement('div');
    v.className = 'widget-metric-value';
    v.textContent = fmtNum(row[c.name]);
    const l = document.createElement('div');
    l.className = 'widget-metric-label';
    l.textContent = humanize(c.name);
    card.append(v, l);
    grid.appendChild(card);
  }
  return grid;
}

function buildBarChart(rows: Record<string, unknown>[], catCol: ColProfile, numCol: ColProfile): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'widget-barchart';
  const title = document.createElement('div');
  title.className = 'widget-title';
  title.textContent = `${humanize(numCol.name)} by ${humanize(catCol.name)}`;
  wrap.appendChild(title);

  const sorted = [...rows].sort((a, b) => (Number(b[numCol.name]) || 0) - (Number(a[numCol.name]) || 0));
  const values = sorted.map(r => Number(r[numCol.name]) || 0);
  const maxVal = Math.max(...values, 1);

  for (let i = 0; i < sorted.length; i++) {
    const row = document.createElement('div');
    row.className = 'widget-bar-row';
    const label = document.createElement('div');
    label.className = 'widget-bar-label';
    label.textContent = String(sorted[i][catCol.name] ?? '');
    const track = document.createElement('div');
    track.className = 'widget-bar-track';
    const fill = document.createElement('div');
    fill.className = 'widget-bar-fill';
    fill.style.width = `${Math.max(2, (values[i] / maxVal) * 100)}%`;
    track.appendChild(fill);
    const val = document.createElement('div');
    val.className = 'widget-bar-value';
    val.textContent = fmtNum(values[i]);
    row.append(label, track, val);
    wrap.appendChild(row);
  }
  return wrap;
}

function buildLineChart(rows: Record<string, unknown>[], dateCol: ColProfile, numCol: ColProfile): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'widget-linechart';
  const title = document.createElement('div');
  title.className = 'widget-title';
  title.textContent = `${humanize(numCol.name)} over ${humanize(dateCol.name)}`;
  wrap.appendChild(title);

  const sorted = [...rows].sort((a, b) => String(a[dateCol.name]).localeCompare(String(b[dateCol.name])));
  const values = sorted.map(r => Number(r[numCol.name]) || 0);
  const maxVal = Math.max(...values);
  const minVal = Math.min(...values, 0);
  const range = maxVal - minVal || 1;

  const W = 520, H = 200, padL = 50, padR = 12, padT = 12, padB = 32;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const xFor = (i: number) => padL + (sorted.length === 1 ? innerW / 2 : (i / (sorted.length - 1)) * innerW);
  const yFor = (v: number) => padT + innerH - ((v - minVal) / range) * innerH;

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'widget-linechart-svg');

  // Axis labels (min + max on Y)
  const axisStyle = 'fill:#6b6b80;font-size:11px;font-family:sans-serif';
  const yMax = document.createElementNS(svgNS, 'text');
  yMax.setAttribute('x', String(padL - 8)); yMax.setAttribute('y', String(padT + 4));
  yMax.setAttribute('text-anchor', 'end'); yMax.setAttribute('style', axisStyle);
  yMax.textContent = fmtNum(maxVal);
  svg.appendChild(yMax);

  const yMin = document.createElementNS(svgNS, 'text');
  yMin.setAttribute('x', String(padL - 8)); yMin.setAttribute('y', String(padT + innerH + 4));
  yMin.setAttribute('text-anchor', 'end'); yMin.setAttribute('style', axisStyle);
  yMin.textContent = fmtNum(minVal);
  svg.appendChild(yMin);

  // Line path
  const d = sorted.map((_, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i)} ${yFor(values[i])}`).join(' ');
  const path = document.createElementNS(svgNS, 'path');
  path.setAttribute('d', d);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', '#2563eb');
  path.setAttribute('stroke-width', '2');
  svg.appendChild(path);

  // Dots
  for (let i = 0; i < sorted.length; i++) {
    const c = document.createElementNS(svgNS, 'circle');
    c.setAttribute('cx', String(xFor(i))); c.setAttribute('cy', String(yFor(values[i])));
    c.setAttribute('r', '3'); c.setAttribute('fill', '#60a5fa');
    svg.appendChild(c);
  }

  // X-axis labels (first, mid, last)
  const xLabelIdxs = sorted.length <= 3
    ? sorted.map((_, i) => i)
    : [0, Math.floor(sorted.length / 2), sorted.length - 1];
  for (const i of xLabelIdxs) {
    const t = document.createElementNS(svgNS, 'text');
    t.setAttribute('x', String(xFor(i))); t.setAttribute('y', String(H - 12));
    t.setAttribute('text-anchor', 'middle'); t.setAttribute('style', axisStyle);
    t.textContent = String(sorted[i][dateCol.name] ?? '').slice(0, 10);
    svg.appendChild(t);
  }

  wrap.appendChild(svg);
  return wrap;
}

function buildStyledTable(rows: Record<string, unknown>[]): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'widget-table-wrap';
  const title = document.createElement('div');
  title.className = 'widget-title';
  title.textContent = `${rows.length} row${rows.length !== 1 ? 's' : ''}`;
  wrap.appendChild(title);
  wrap.appendChild(buildTable(rows));
  return wrap;
}

function buildRawPane(rows: Record<string, unknown>[], rowCount: number): HTMLElement {
  const wrap = document.createElement('div');
  const label = document.createElement('div');
  label.className = 'pane-label';
  label.textContent = `${rowCount} row${rowCount !== 1 ? 's' : ''}`;
  wrap.appendChild(label);
  wrap.appendChild(buildTable(rows));
  return wrap;
}

function buildSqlPane(sql: string): HTMLElement {
  const wrap = document.createElement('div');
  if (!sql) {
    const empty = document.createElement('div');
    empty.className = 'pane-empty';
    empty.textContent = 'No SQL was generated.';
    wrap.appendChild(empty);
    return wrap;
  }
  wrap.appendChild(buildCode(sql));
  return wrap;
}

function buildResponsesPane(calls: ClaudeInteraction[], summary: string): HTMLElement {
  const wrap = document.createElement('div');

  if (summary) {
    const section = document.createElement('div');
    section.className = 'pane-section';
    const lbl = document.createElement('div');
    lbl.className = 'pane-label';
    lbl.textContent = 'Final summary (spoken to user)';
    const p = document.createElement('p');
    p.className = 'report-entry-summary';
    p.textContent = summary;
    section.append(lbl, p);
    wrap.appendChild(section);
  }

  if (!calls || calls.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'pane-empty';
    empty.textContent = 'No Claude interactions were recorded.';
    wrap.appendChild(empty);
    return wrap;
  }

  const section = document.createElement('div');
  section.className = 'pane-section';
  const lbl = document.createElement('div');
  lbl.className = 'pane-label';
  lbl.textContent = `Claude back-and-forth (${calls.length} calls)`;
  section.appendChild(lbl);
  section.appendChild(buildClaudeLog(calls));
  wrap.appendChild(section);
  return wrap;
}

// ── Shared builders ─────────────────────────────────────────────────────────

function buildCode(sql: string): HTMLElement {
  const pre = document.createElement('pre');
  pre.className = 'report-sql';
  const code = document.createElement('code');
  code.textContent = sql;
  pre.appendChild(code);
  return pre;
}

function buildTable(rows: Record<string, unknown>[]): HTMLElement {
  if (!rows || rows.length === 0) {
    const p = document.createElement('p');
    p.className = 'report-no-data';
    p.textContent = 'No rows returned.';
    return p;
  }
  const cols = Object.keys(rows[0]);
  // Sort by id column if one exists, ascending
  const idCol = cols.find(c => c.toLowerCase() === 'id') ?? cols.find(c => c.toLowerCase().endsWith('_id'));
  if (idCol) {
    rows = [...rows].sort((a, b) => {
      const av = a[idCol], bv = b[idCol];
      if (typeof av === 'number' && typeof bv === 'number') return av - bv;
      return String(av ?? '').localeCompare(String(bv ?? ''));
    });
  }
  const scroll = document.createElement('div');
  scroll.className = 'table-scroll';
  const table = document.createElement('table');
  table.className = 'report-data-table';
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  for (const col of cols) {
    const th = document.createElement('th');
    th.textContent = col;
    hr.appendChild(th);
  }
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const col of cols) {
      const td = document.createElement('td');
      td.textContent = String(row[col] ?? '');
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  scroll.appendChild(table);
  return scroll;
}

function buildClaudeLog(calls: ClaudeInteraction[]): HTMLElement {
  const list = document.createElement('div');
  list.className = 'claude-log';
  calls.forEach((call, idx) => {
    const item = document.createElement('details');
    item.className = 'claude-call';
    const summary = document.createElement('summary');
    summary.className = 'claude-call-summary';
    const step = document.createElement('span');
    step.className = 'claude-call-step';
    step.textContent = `${idx + 1}. ${call.step || 'Claude call'}`;
    const tokens = document.createElement('span');
    tokens.className = 'claude-call-tokens';
    const ins = call.input_tokens ?? 0;
    const outs = call.output_tokens ?? 0;
    const ms = call.latency_ms ?? 0;
    tokens.textContent = `${ins} in · ${outs} out · ${ms}ms`;
    summary.append(step, tokens);
    item.appendChild(summary);

    const body = document.createElement('div');
    body.className = 'claude-call-body';
    if (call.system) body.appendChild(claudeBlock('System', call.system));
    if (call.user_message) body.appendChild(claudeBlock('User', call.user_message));
    if (call.response) body.appendChild(claudeBlock('Response', call.response));
    item.appendChild(body);
    list.appendChild(item);
  });
  return list;
}

function claudeBlock(label: string, text: string): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'claude-block';
  const lbl = document.createElement('div');
  lbl.className = 'claude-block-label';
  lbl.textContent = label;
  const pre = document.createElement('pre');
  pre.className = 'claude-block-text';
  pre.textContent = text;
  wrap.appendChild(lbl);
  wrap.appendChild(pre);
  return wrap;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
