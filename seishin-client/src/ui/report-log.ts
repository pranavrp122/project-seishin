import { ReportLogEntry } from '../types.ts';

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
    empty.textContent = 'No reports yet.';
    logContainer.appendChild(empty);
    return;
  }

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
  const cols = Object.keys(rows[0]);
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
