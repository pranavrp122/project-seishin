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
  tabPanes.dashboard = buildDashboardPane(entry.dashboardB64);
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

function buildDashboardPane(b64: string): HTMLElement {
  const wrap = document.createElement('div');
  if (!b64) {
    const empty = document.createElement('div');
    empty.className = 'pane-empty';
    empty.textContent = 'No dashboard image was generated for this report.';
    wrap.appendChild(empty);
    return wrap;
  }
  const img = document.createElement('img');
  img.className = 'dashboard-img';
  img.src = `data:image/png;base64,${b64}`;
  img.alt = 'Report dashboard';
  wrap.appendChild(img);
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
