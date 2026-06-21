# Function Definition Guide

Best practices for defining functions (tools) for voice agents using the Deepgram Voice Agent API.

## Core Principle

Function descriptions teach the LLM when and how to call functions. Write them as instructions to a colleague, not as developer documentation.

## Anatomy of a Function Definition

```python
ThinkSettingsV1FunctionsItem(
    name="check_available_slots",
    description="What it does, when to use it, and any workflow requirements",
    parameters={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "What it is and format requirements"
            }
        },
        "required": ["date"]
    }
)
```

The function definition is sent to Deepgram as part of the agent configuration. The LLM sees the name, description, and parameters when deciding whether to call a function.

## Writing Descriptions

Use a three-part formula: **What**, **When**, **How**.

```python
description="""Check available appointment slots.

Call this when a patient asks about availability.
You can optionally filter by date and/or provider.
If the patient doesn't specify, omit the parameters
to get a general overview.

This is a read-only lookup - no confirmation needed."""
```

### What to Include

- What the function does (one sentence)
- When to call it (triggers)
- Any pre-conditions (confirm with the caller first?)
- What the result means (if not obvious)

### What to Omit

- Implementation details (the LLM doesn't care about your database)
- Error handling instructions (handle errors in your code, not the prompt)
- Response format details (the LLM adapts to whatever JSON you return)

## Confirm-Then-Act Pattern

For functions that change state, the description must instruct the LLM to get confirmation first:

```python
description="""Book an appointment for a patient.

IMPORTANT: Before calling this function, you MUST:
1. Confirm the appointment details with the patient
   (date, time, provider, service type)
2. Collect the patient's name and phone number
3. WAIT for the patient to say "yes" or confirm

Only call this after the patient has explicitly agreed."""
```

Without this, the LLM will call the function as soon as it has the parameters, skipping confirmation.

For read-only functions, explicitly say no confirmation is needed:

```python
description="""Check available appointment slots.

This is a read-only lookup - no confirmation needed before calling."""
```

## Voice-Specific Parameter Descriptions

Voice agents hear speech, not text. Teach the LLM to parse natural language into structured parameters:

```python
"date": {
    "type": "string",
    "description": "Date in YYYY-MM-DD format. If the patient says "
                   "'Monday' or 'next week', convert to a specific date."
}
```

```python
"patient_phone": {
    "type": "string",
    "description": "Patient phone number"
}
```

The LLM is generally good at converting spoken numbers to digits, but explicit format instructions help with edge cases.

## Parameter Design

### Use `required` Carefully

Only require parameters that are truly necessary. Optional parameters with good descriptions give the LLM flexibility:

```python
"properties": {
    "date": {
        "type": "string",
        "description": "Date to check. Omit to see all upcoming availability."
    },
    "provider": {
        "type": "string",
        "description": "Provider name to filter by. Omit to see all providers."
    }
},
"required": []  # Both are optional
```

### Use Enums to Constrain Values

```python
"reason": {
    "type": "string",
    "description": "Why the call is ending",
    "enum": ["appointment_booked", "customer_goodbye", "no_action_needed"]
}
```

Enums prevent the LLM from inventing values and make your function handler simpler.

## Coordinating with the System Prompt

Function descriptions and the system prompt should reinforce each other. If a function requires confirmation before calling, say so in both places:

**In the function description:**
```python
description="...WAIT for the patient to confirm before calling..."
```

**In the system prompt:**
```
For book_appointment:
- FIRST confirm the details with the patient
- WAIT for the patient to confirm
- THEN call book_appointment
```

Redundancy is intentional. The LLM sees both the prompt and the function descriptions, and reinforcing critical behaviors in both locations makes them more reliable.

## Designing Return Values

The result you return from a function call becomes context for the LLM's next response. Design results for the LLM to read, not for a frontend to render:

```python
# Good - the LLM can speak this naturally
return {
    "available_slots": [
        {
            "slot_id": "slot-abc123",
            "description": "Cleaning with Lisa Thompson on 2026-03-03 at 10:00 AM"
        }
    ],
    "total_available": 3,
}

# Bad - raw data the LLM has to interpret
return {
    "slots": [{"id": "abc", "t": 1736240400, "p": "LT", "type": 1}]
}
```

Include a `description` or `message` field with human-readable text. The LLM will use it almost verbatim, which gives you more control over what gets said.

### Error Results

Return errors as structured data, not exceptions:

```python
return {
    "success": False,
    "error": "That slot is no longer available. Please check availability again."
}
```

The LLM will incorporate the error message into its response naturally: "I'm sorry, it looks like that slot is no longer available. Would you like me to check for other openings?"

## How Many Functions?

Keep it to 2-5 functions per agent. More functions mean:
- The LLM has more choices to evaluate, increasing latency
- Higher chance of the LLM calling the wrong function
- Longer configuration messages sent to Deepgram

If you need more than 5 functions, consider whether some can be combined or whether you need a multi-agent architecture.

## Example: Complete Function Set

This reference implementation uses 5 functions:

| Function | Purpose | Confirmation Required? |
|---|---|---|
| `check_available_slots` | Look up open time slots | No (read-only) |
| `book_appointment` | Book a specific slot | Yes |
| `check_appointment` | Look up existing appointment | No (read-only) |
| `cancel_appointment` | Cancel an appointment | Yes |
| `end_call` | Hang up the phone | No (natural conclusion) |

The read-only / write distinction maps directly to whether confirmation is needed.

## See Also

- `voice_agent/agent_config.py` - The function definitions used in this reference
- `voice_agent/function_handlers.py` - How function calls are dispatched to the backend
- [PROMPT_GUIDE.md](PROMPT_GUIDE.md) - System prompt best practices
