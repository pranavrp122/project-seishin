import { onStateChange, appState } from '../state.ts';
import { EmailResult } from '../types.ts';

let cardsContainer: HTMLDivElement | null = null;

/** Render email result cards into a parent container. Reacts to state.emailResults. */
export function renderEmailCards(parent: HTMLElement): void {
  cardsContainer = document.createElement('div');
  cardsContainer.className = 'email-cards-container';
  parent.appendChild(cardsContainer);

  onStateChange(renderCards);
  renderCards(appState);
}

function renderCards(state: typeof appState): void {
  if (!cardsContainer) return;
  while (cardsContainer.firstChild) cardsContainer.removeChild(cardsContainer.firstChild);

  if (!state.emailResults || state.emailResults.length === 0) {
    cardsContainer.style.display = 'none';
    return;
  }
  cardsContainer.style.display = 'block';

  const header = document.createElement('div');
  header.className = 'email-cards-header';
  const n = state.emailResults.length;
  header.textContent = `${n} email${n !== 1 ? 's' : ''}`;
  cardsContainer.appendChild(header);

  const list = document.createElement('div');
  list.className = 'email-cards-list';
  for (const e of state.emailResults) list.appendChild(buildCard(e));
  cardsContainer.appendChild(list);
}

function buildCard(email: EmailResult): HTMLElement {
  const card = document.createElement('div');
  card.className = 'email-card';

  const sender = document.createElement('div');
  sender.className = 'email-card-sender';
  sender.textContent = email.sender;
  card.appendChild(sender);

  const subject = document.createElement('div');
  subject.className = 'email-card-subject';
  subject.textContent = email.subject;
  card.appendChild(subject);

  const snippet = document.createElement('div');
  snippet.className = 'email-card-snippet';
  snippet.textContent = email.snippet.length > 120
    ? email.snippet.slice(0, 120) + '...'
    : email.snippet;
  card.appendChild(snippet);

  const time = document.createElement('div');
  time.className = 'email-card-time';
  time.textContent = email.timestamp;
  card.appendChild(time);

  return card;
}
