import { ReportLogEntry, ClaudeInteraction } from '../types.ts';

let logContainer: HTMLDivElement | null = null;
const entries: ReportLogEntry[] = [];

export function renderReportLog(parent: HTMLElement): void {
  logContainer = document.createElement('div');
  logContainer.id = 'report-log-list';
  logContainer.className = 'report-log-list';
  parent.appendChild(logContainer);
  renderEntries(); // paint the empty state immediately
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
    hint.textContent = 'Ask for a report and it\'ll show up here with the SQL and raw data.';

    const example = document.createElement('div');
    example.className = 'report-log-empty-example';
    example.textContent = 'e.g. "how many orders did we have this year"';

    empty.append(icon, heading, hint, example);
    logContainer.appendChild(empty);
    return;
  }

  // Header shown when we have entries
  const header = document.createElement('div');
  header.className = 'report-log-header';
  header.textContent = `Session reports · ${entries.length}`;
  logContainer.appendChild(header);

  for (const entry of entries) {
    logContainer.appendChild(buildEntryEl(entry));
  }
}

function buildEntryEl(entry: ReportLogEntry): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'report-entry';

  // Header bar — always visible, click to expand
  const header = document.createElement('div');
  header.className = 'report-entry-header';

  const title = document.createElement('span');
  title.className = 'report-entry-title';
  title.textContent = entry.query;

  const meta = document.createElement('span');
  meta.className = 'report-entry-meta';
  meta.textContent = `${entry.rowCount} row${entry.rowCount !== 1 ? 's' : ''} · ${formatTime(entry.timestamp)}`;

  const chevron = document.createElement('span');
  chevron.className = 'report-entry-chevron';
  chevron.textContent = '▸';

  header.appendChild(title);
  header.appendChild(meta);
  header.appendChild(chevron);
  wrap.appendChild(header);

  // Detail panel — hidden until expanded
  const detail = document.createElement('div');
  detail.className = 'report-entry-detail';
  detail.style.display = 'none';
  if (entry.claudeInteractions.length > 0) {
    detail.appendChild(buildSection(
      `Claude Back-and-Forth (${entry.claudeInteractions.length} calls)`,
      buildClaudeLog(entry.claudeInteractions),
    ));
  }
  detail.appendChild(buildSection('SQL', buildCode(entry.sql)));
  detail.appendChild(buildSection(`Raw Data (${entry.rowCount} rows)`, buildTable(entry.results)));
  if (entry.summary) {
    const summaryEl = document.createElement('p');
    summaryEl.className = 'report-entry-summary';
    summaryEl.textContent = entry.summary;
    detail.appendChild(buildSection('Summary', summaryEl));
  }
  wrap.appendChild(detail);

  // Toggle on header click
  header.addEventListener('click', () => {
    const open = detail.style.display !== 'none';
    detail.style.display = open ? 'none' : 'block';
    chevron.textContent = open ? '▸' : '▾';
    wrap.classList.toggle('open', !open);
  });

  return wrap;
}

function buildSection(label: string, content: HTMLElement): HTMLElement {
  const section = document.createElement('div');
  section.className = 'report-detail-section';
  const heading = document.createElement('div');
  heading.className = 'report-detail-label';
  heading.textContent = label;
  section.appendChild(heading);
  section.appendChild(content);
  return section;
}

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
  // Sort by id column if one exists, ascending
  const cols = Object.keys(rows[0]);
  const idCol = cols.find(c => c.toLowerCase() === 'id') ?? cols.find(c => c.toLowerCase().endsWith('_id'));
  if (idCol) {
    rows = [...rows].sort((a, b) => {
      const av = a[idCol], bv = b[idCol];
      if (typeof av === 'number' && typeof bv === 'number') return av - bv;
      return String(av ?? '').localeCompare(String(bv ?? ''));
    });
  }
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
  return table;
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
    summary.appendChild(step);
    summary.appendChild(tokens);
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
