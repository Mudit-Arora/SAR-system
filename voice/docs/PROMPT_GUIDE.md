# Voice Agent Prompt Guide

Best practices for writing prompts for voice agents using the Deepgram Voice Agent API.

## Core Principle: Voice-First Design

You're writing a script for a voice actor, not a chat interface. Every word the agent generates is synthesized into speech and played over a phone call. If it sounds awkward when read aloud, it will sound awkward when spoken.

## Critical Formatting Rules

Your prompt must explicitly forbid patterns that don't work in voice:

```
VOICE FORMATTING RULES:
You are a VOICE agent. Your responses are spoken aloud via text-to-speech.
- Use only plain conversational language
- NO markdown, emojis, brackets, or special formatting
- Keep responses brief: 1-2 sentences per turn
- Never announce function calls
- Spell out numbers naturally (say "January third" not "1/3")
```

### Why This Matters

```
Bad:  "That's great! 😊"
TTS:  "That's great exclamation point smiley face"

Bad:  "**Important**: Check your email"
TTS:  "star star Important star star colon Check your email"

Bad:  "[Looking up your appointment...]"
TTS:  "bracket Looking up your appointment dot dot dot bracket"

Good: "That's wonderful!"
TTS:  "That's wonderful!"
```

Without explicit instructions, LLMs default to chat-style formatting. The voice formatting rules block must be prominent in your prompt.

## Voice-Friendly Patterns

### Numbers and Identifiers

```
Bad:  "Your appointment is on 3/3/2026"
Good: "Your appointment is on January seventh"

Bad:  "That'll be $150.00"
Good: "That'll be one hundred and fifty dollars"

Bad:  "Call 555-1234"
Good: "Call five five five, one two three four"
```

### Lists

```
Bad:  "You have three options: 1) Basic, 2) Premium, 3) Enterprise"
Good: "You have three options. The first is Basic, then Premium,
       and finally Enterprise."
```

### Confirmations

```
Bad:  "Appointment Details:
       - Date: Jan 7
       - Time: 10:00 AM
       - Provider: Dr. Chen"

Good: "I have a checkup with Doctor Chen on January seventh at ten AM."
```

## Prompt Structure

A voice agent prompt should cover these sections:

### 1. Identity and Personality

```
You are a friendly and professional receptionist at Bright Smile Dental,
a family dental practice. You are answering an incoming phone call.
```

Keep it concise. The agent needs to know who it is and what the interaction mode is (phone call, not chat).

### 2. Voice Formatting Rules

Always include these explicitly. See above.

### 3. Responsibilities

```
YOUR RESPONSIBILITIES:
1. Greet callers warmly and identify their needs
2. Help with appointment scheduling
3. Answer basic questions about the practice
4. End calls gracefully
```

### 4. Domain Knowledge

```
PRACTICE INFORMATION:
- Name: Bright Smile Dental
- Hours: Monday through Friday, 9 AM to 5 PM
- Providers:
  - Dr. Sarah Chen (general dentistry)
  - Lisa Thompson, RDH (cleanings)
```

Give the agent the facts it needs. Without this, it will either make things up or say "I don't have that information" for basic questions.

### 5. Function Call Rules

```
FUNCTION CALL RULES:

For check_available_slots:
- Call this whenever a patient asks about availability
- No confirmation needed - it's a read-only lookup

For book_appointment:
- FIRST confirm the details with the patient
- WAIT for the patient to confirm
- THEN call book_appointment
```

Be explicit about the confirm-then-act pattern for destructive operations. Without this, the agent will call functions before getting confirmation.

### 6. Conversation Style

```
CONVERSATION STYLE:
- Be warm but efficient
- Ask one question at a time
- If a patient is vague, ask what they need
- Always confirm details before booking
```

## Key Patterns

### Confirm-Then-Act

For operations that change state (booking, canceling), the agent should:

1. Summarize what it's about to do
2. Ask for confirmation
3. Wait for the caller to say "yes"
4. Then call the function

```
Agent: "I have a cleaning with Lisa Thompson on Tuesday at 10 AM.
        Shall I book that for you?"
Caller: "Yes please."
[Agent calls book_appointment]
```

Without this pattern, the agent tends to call functions immediately after gathering information, before the caller has confirmed.

### Read-Only Lookups

For operations that don't change state (checking availability, looking up appointments), the agent can call the function without asking permission:

```
Caller: "What do you have available next Tuesday?"
[Agent calls check_available_slots - no confirmation needed]
Agent: "I have openings at 10 AM and 2 PM with Lisa Thompson."
```

### One Question at a Time

Voice conversations are sequential. Asking multiple questions in one turn confuses callers:

```
Bad:  "What's your name, phone number, and preferred date?"
Good: "Can I get your name?"
      [wait]
      "And your phone number?"
      [wait]
      "When would you like to come in?"
```

### Don't Announce Function Calls

```
Bad:  "Let me check that for you... [pause while function runs]... I found..."
Good: "I have openings at 10 AM and 2 PM."
```

The function call happens between turns. The caller doesn't need to know about it. Just present the result naturally.

### Graceful Endings

```
Good: "You're welcome! We'll see you on Tuesday. Have a great day!"
[Agent calls end_call]
```

Say goodbye first, then call the `end_call` function. Don't generate text after calling it.

## Testing Your Prompt

1. Run the server and dev client locally
2. Have a conversation - does the agent stay in character?
3. Try edge cases:
   - Ask for something outside scope ("Do you do root canals?")
   - Give vague requests ("I need to come in")
   - Interrupt the agent mid-sentence (barge-in)
   - Ask to cancel without having an appointment
4. Check the transcript in the server logs - are responses 1-2 sentences?
5. Listen for unnatural phrasing - if it sounds wrong spoken aloud, rewrite it

## See Also

- `voice_agent/agent_config.py` - The dental receptionist prompt (working example)
- [FUNCTION_GUIDE.md](FUNCTION_GUIDE.md) - Function definition best practices
