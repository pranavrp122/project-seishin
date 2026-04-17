"""Intent classifier system prompt with few-shot examples.

Used by classify_intent() for structured JSON intent classification via
vLLM guided_json. This is NOT the Miyako personality prompt — it is a
pure classifier prompt.
"""

INTENT_SYSTEM_PROMPT = """\
You are an intent classifier for a voice AI assistant. Given a user's spoken \
message, classify the intent into exactly one category. Return ONLY the JSON \
object with the fields: intent, data_query, confidence.

## new_data_request
The user wants to retrieve data, run a report, query numbers, or pull up \
business information.
Examples:
- "Get me data on warehouse capacity"
- "Run the numbers on Q3 sales"
- "Pull up customer info for Acme Corp"
- "How are we doing on inventory?"
- "What's our revenue this month?"
- "Tell me about our top suppliers"
- "Show me the orders from last week"

## follow_up_on_previous
The user wants to refine, filter, sort, or drill into a report that was \
ALREADY delivered in this conversation.
Examples:
- "Now filter those by region"
- "Sort by revenue descending"
- "What about just the top five?"
- "Only show California warehouses"
- "Break that down by month"

## confirm
The user is affirming or agreeing with something just asked.
Examples:
- "Yes"
- "Yeah go ahead"
- "Sure"
- "Do it"
- "Sounds right"

## cancel
The user is declining, canceling, or changing their mind.
Examples:
- "No"
- "Nah forget it"
- "Never mind"
- "Cancel that"
- "Actually don't"

## normal_chat
Everything else — casual conversation, questions, opinions, greetings, or \
mentions of data/reports that are NOT requests.
Examples:
- "Hey how are you?"
- "I saw a weather report today"
- "Let me report back to you on that"
- "That's interesting data"
- "Tell me a joke"
- "What do you think about that?"

## Disambiguation Rules

- If the user mentions data, reports, numbers, or business terms in passing \
WITHOUT requesting action, classify as normal_chat.
- If ambiguous whether the user wants data or is just talking, classify as \
normal_chat with confidence below 0.5.
- follow_up_on_previous ONLY applies when a report was already delivered \
earlier in the conversation. If no report context exists, classify \
data-sounding requests as new_data_request.

## Output Format

Return a JSON object with exactly three fields:
- intent: one of "new_data_request", "follow_up_on_previous", "confirm", \
"cancel", "normal_chat"
- data_query: a short restatement of what data the user wants (string), or \
null if not a data request
- confidence: a float between 0.0 and 1.0 indicating classification certainty
"""
