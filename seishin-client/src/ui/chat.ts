import { onStateChange, appState, updateState } from '../state.ts';
import { ChatMessage } from '../types.ts';

let chatContainer: HTMLDivElement | null = null;
let interimEl: HTMLDivElement | null = null;

// Regex to strip emotion/physical/pause tags like [happy], [long-break], etc. from display text.
// Matches anywhere in the text (not just leading) so mid-sentence tags are removed too.
const EMOTION_TAG_RE = /\[[a-z][a-z\s-]{0,30}\]\s*/gi;

/** Strip Fish Speech emotion tags from text for display */
function stripEmotionTag(text: string): string {
  return text.replace(EMOTION_TAG_RE, '').replace(/\s+/g, ' ').trim();
}

/** Remove all child elements from a container safely */
function clearChildren(el: HTMLElement): void {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

/**
 * Render the chat container into the given parent element.
 * Sets up state change listener for reactive updates.
 */
export function renderChat(parent: HTMLElement): void {
  chatContainer = document.createElement('div');
  chatContainer.id = 'chat-container';
  chatContainer.className = 'chat-container';
  parent.appendChild(chatContainer);

  // Interim transcript indicator (bottom of chat area)
  interimEl = document.createElement('div');
  interimEl.id = 'interim-transcript';
  interimEl.className = 'interim-transcript';
  parent.appendChild(interimEl);

  onStateChange(renderMessages);
  renderMessages(appState);
}

function renderMessages(state: typeof appState): void {
  if (!chatContainer || !interimEl) return;

  // Rebuild chat messages using safe DOM methods
  clearChildren(chatContainer);
  for (const msg of state.messages) {
    // Skip companion messages that are still pending (text-audio sync per D-11)
    if (msg.role === 'companion' && msg.audioState === 'pending') continue;

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-companion'}`;

    const textSpan = document.createElement('span');
    textSpan.className = 'chat-text';
    textSpan.textContent = msg.role === 'companion'
      ? stripEmotionTag(msg.text)
      : msg.text;
    bubble.appendChild(textSpan);

    chatContainer.appendChild(bubble);
  }

  // Auto-scroll to bottom
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // Update interim transcript per D-09
  if (state.interimTranscript) {
    interimEl.textContent = state.interimTranscript;
    interimEl.style.display = 'block';
  } else {
    interimEl.textContent = '';
    interimEl.style.display = 'none';
  }
}

/**
 * Show a companion sentence in the chat when its audio begins playing.
 * Called by the orchestrator's sync polling loop per D-11.
 * Marks the first pending companion message as 'playing' so it renders.
 */
export function showSentence(_sentenceIdx: number, _text: string): void {
  // Find the first companion message with audioState 'pending' and mark it playing
  for (const msg of appState.messages) {
    if (msg.role === 'companion' && msg.audioState === 'pending') {
      msg.audioState = 'playing';
      // Trigger re-render via state update
      updateState({ messages: [...appState.messages] });
      return;
    }
  }
}

/** Mark all companion messages in the current response as complete */
export function markResponseComplete(): void {
  let changed = false;
  for (const msg of appState.messages) {
    if (msg.role === 'companion' && (msg.audioState === 'pending' || msg.audioState === 'playing')) {
      msg.audioState = 'complete';
      changed = true;
    }
  }
  if (changed) {
    updateState({ messages: [...appState.messages] });
  }
}

/** Mark current response as interrupted, remove unplayed pending sentences */
export function markResponseInterrupted(): void {
  // Remove pending (unshown) companion messages
  const filtered = appState.messages.filter(
    (msg: ChatMessage) => !(msg.role === 'companion' && msg.audioState === 'pending')
  );
  // Mark any playing messages as complete
  for (const msg of filtered) {
    if (msg.role === 'companion' && msg.audioState === 'playing') {
      msg.audioState = 'complete';
    }
  }
  updateState({ messages: filtered });
}
