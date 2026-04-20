import { openPath, revealItemInDir } from '@tauri-apps/plugin-opener';
import { onStateChange, appState } from '../state.ts';
import { FileResult } from '../types.ts';

let cardsContainer: HTMLDivElement | null = null;

/** Render file result cards into a parent container. Reacts to state.fileResults. */
export function renderFileCards(parent: HTMLElement): void {
  cardsContainer = document.createElement('div');
  cardsContainer.className = 'file-cards-container';
  parent.appendChild(cardsContainer);

  onStateChange(renderCards);
  renderCards(appState);
}

function renderCards(state: typeof appState): void {
  if (!cardsContainer) return;
  while (cardsContainer.firstChild) cardsContainer.removeChild(cardsContainer.firstChild);

  if (!state.fileResults || state.fileResults.length === 0) {
    cardsContainer.style.display = 'none';
    return;
  }
  cardsContainer.style.display = 'block';

  const header = document.createElement('div');
  header.className = 'file-cards-header';
  const n = state.fileResults.length;
  header.textContent = `${n} file${n !== 1 ? 's' : ''} found`;
  cardsContainer.appendChild(header);

  const list = document.createElement('div');
  list.className = 'file-cards-list';
  for (const f of state.fileResults) list.appendChild(buildCard(f));
  cardsContainer.appendChild(list);
}

function buildCard(file: FileResult): HTMLElement {
  const card = document.createElement('div');
  card.className = 'file-card';

  const top = document.createElement('div');
  top.className = 'file-card-top';

  const icon = document.createElement('span');
  icon.className = 'file-card-icon';
  icon.textContent = iconForType(file.file_type);
  top.appendChild(icon);

  const info = document.createElement('div');
  info.className = 'file-card-info';

  const name = document.createElement('div');
  name.className = 'file-card-name';
  name.textContent = file.name;
  info.appendChild(name);

  const meta = document.createElement('div');
  meta.className = 'file-card-meta';
  const folder = document.createElement('span');
  folder.textContent = `📁 ${shortenPath(file.dir)}`;
  const sep1 = document.createElement('span');
  sep1.className = 'file-card-sep';
  sep1.textContent = ' · ';
  const modified = document.createElement('span');
  modified.textContent = `🕐 ${file.modified_label}`;
  const sep2 = document.createElement('span');
  sep2.className = 'file-card-sep';
  sep2.textContent = ' · ';
  const size = document.createElement('span');
  size.textContent = formatSize(file.size_bytes);
  meta.append(folder, sep1, modified, sep2, size);
  info.appendChild(meta);

  top.appendChild(info);
  card.appendChild(top);

  const actions = document.createElement('div');
  actions.className = 'file-card-actions';

  const openBtn = document.createElement('button');
  openBtn.className = 'file-card-btn file-card-btn-primary';
  openBtn.textContent = 'Open';
  openBtn.addEventListener('click', async () => {
    const winPath = pathToWindows(file.path);
    console.log('[file-cards] opening:', winPath);
    try {
      await openPath(winPath);
    } catch (err) {
      console.error('[file-cards] open failed:', err);
      alert(`Could not open file:\n${winPath}\n\n${err}`);
    }
  });

  const revealBtn = document.createElement('button');
  revealBtn.className = 'file-card-btn';
  revealBtn.textContent = 'Show in folder';
  revealBtn.addEventListener('click', async () => {
    const winPath = pathToWindows(file.path);
    console.log('[file-cards] revealing:', winPath);
    try {
      await revealItemInDir(winPath);
    } catch (err) {
      console.error('[file-cards] reveal failed:', err);
      alert(`Could not reveal file:\n${winPath}\n\n${err}`);
    }
  });

  actions.append(openBtn, revealBtn);
  card.appendChild(actions);

  return card;
}

function iconForType(ext: string): string {
  const e = (ext || '').toLowerCase();
  if (e === 'pdf') return '📄';
  if (['doc', 'docx'].includes(e)) return '📝';
  if (['xls', 'xlsx', 'csv'].includes(e)) return '📊';
  if (['ppt', 'pptx'].includes(e)) return '📑';
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic'].includes(e)) return '🖼️';
  if (['mp4', 'mov', 'avi', 'mkv'].includes(e)) return '🎞️';
  if (['mp3', 'wav', 'm4a', 'flac'].includes(e)) return '🎵';
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(e)) return '🗜️';
  if (['txt', 'md', 'rtf'].includes(e)) return '📃';
  return '📎';
}

function shortenPath(dir: string): string {
  const home = dir.match(/^\/mnt\/c\/Users\/[^\/]+/);
  if (home) return '~' + dir.slice(home[0].length);
  return dir;
}

/** WSL path → Windows path for Tauri opener (Tauri runs on Windows).
 *  Uses forward slashes since Windows accepts both and Tauri opener docs show them. */
function pathToWindows(wslPath: string): string {
  const m = wslPath.match(/^\/mnt\/([a-z])\/(.*)$/);
  if (!m) return wslPath;
  return `${m[1].toUpperCase()}:/${m[2]}`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
