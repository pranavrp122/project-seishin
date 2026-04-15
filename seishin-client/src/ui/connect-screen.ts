// Placeholder - Task 2 will implement full connect screen
let connectEl: HTMLDivElement | null = null;

export function renderConnectScreen(parent: HTMLElement): void {
  connectEl = document.createElement('div');
  connectEl.id = 'connect-screen';
  parent.appendChild(connectEl);
}

export function hideConnectScreen(): void {
  if (connectEl) connectEl.style.display = 'none';
}

export function showConnectScreen(): void {
  if (connectEl) connectEl.style.display = 'flex';
}
