"""
Function dispatch - routes agent function calls to the backend SAR service.

Each function the agent can call (defined in agent_config.py) maps to a method
on the SAR service.  This module is the bridge between the voice agent layer
and the backend layer.

The SAR service reads live state from the integration server's /ops endpoint
(or a built-in snapshot when that's unreachable), so the voice agent layer
doesn't know or care where the search state comes from.
"""
import logging

logger = logging.getLogger(__name__)


async def dispatch_function(name: str, args: dict) -> dict:
    """Dispatch a function call to the appropriate backend handler.

    Args:
        name: Function name (matches names in agent_config.FUNCTIONS)
        args: Parsed arguments from the LLM

    Returns:
        Result dict that gets sent back to the agent as context for its next response.
    """
    # Lazy import - keeps the backend dependency explicit and avoids
    # circular imports during startup.
    from backend.sar_service import sar_service

    if name == "get_search_status":
        return await sar_service.get_search_status()

    elif name == "get_highest_probability_area":
        return await sar_service.get_highest_probability_area()

    elif name == "get_coverage":
        return await sar_service.get_coverage()

    elif name == "get_located_status":
        return await sar_service.get_located_status()

    elif name == "end_call":
        reason = args.get("reason", "customer_goodbye")
        logger.info(f"Call ending: {reason}")
        return {"status": "call_ended", "reason": reason}

    else:
        logger.warning(f"Unknown function: {name}")
        return {"error": f"Unknown function: {name}"}
