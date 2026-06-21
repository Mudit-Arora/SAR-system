"""
Function dispatch - routes agent function calls to their handlers.

Each function the agent can call (defined in agent_config.py) is handled here.
The SAR operator agent has a single function: end_call, fired only once the
person reports seeing the search drone.
"""
import logging

logger = logging.getLogger(__name__)


async def dispatch_function(name: str, args: dict) -> dict:
    """Dispatch a function call to the appropriate handler.

    Args:
        name: Function name (matches names in agent_config.FUNCTIONS)
        args: Parsed arguments from the LLM

    Returns:
        Result dict that gets sent back to the agent as context for its next response.
    """
    if name == "end_call":
        reason = args.get("reason", "drone_sighted")
        logger.info(f"Call ending: {reason}")
        return {"status": "call_ended", "reason": reason}

    else:
        logger.warning(f"Unknown function: {name}")
        return {"error": f"Unknown function: {name}"}
