"""
agent.py

A small Fit Finder agent loop. It keeps session state, decides which action to
take next, and records the actions it took while working toward a result.
"""

import json
import os
import re

from tools import _get_groq_client, create_fit_card, search_listings, suggest_outfit


_PLANNER_MODEL = os.environ.get("FITFINDER_AGENT_MODEL", "llama-3.3-70b-versatile")

_DETERMINISTIC_EXPLANATIONS = {
    "parse_query":    "Extracting the search criteria from the user's natural language query.",
    "search":         "Searching the listings catalog with the current constraints.",
    "select_item":    "Choosing the best match by scoring each result against the user's wardrobe.",
    "fail_no_results":"Giving up — no results were found after exhausting all constraint relaxations.",
    "finish":         "All steps complete — returning results to the user.",
}
_ACTION_PRIORITY = [
    "parse_query",
    "search",
    "relax_price",
    "relax_size",
    "select_item",
    "suggest_outfit",
    "create_fit_card",
    "fail_no_results",
    "finish",
]


def _new_session(query: str, wardrobe: dict, listings: list | None = None) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "listings": listings,
        "parsed": {},
        "current_constraints": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        "notes": [],
        "search_attempts": [],
        "tool_history": [],
        "planner_history": [],
        "search_status": "not_started",
        "relaxations": {"price": False, "size": False},
    }


def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.

    Handles patterns like:
      "vintage graphic tee under $30, size M"
      "90s track jacket in size M"
      "black combat boots size 8"
    """
    text = query

    max_price = None
    price_match = re.search(
        r"(?:under|below|max|for)\s+\$(\d+(?:\.\d+)?)", text, re.IGNORECASE
    )
    if not price_match:
        price_match = re.search(r"\$(\d+(?:\.\d+)?)", text)
    if price_match:
        max_price = float(price_match.group(1))
        text = text[: price_match.start()] + text[price_match.end() :]

    size = None
    size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)", text, re.IGNORECASE)
    if size_match:
        size = size_match.group(1)
        text = text[: size_match.start()] + text[size_match.end() :]

    description = re.sub(r"\s+", " ", text).strip().strip(",").strip()
    return {"description": description, "size": size, "max_price": max_price}


def _record_action(session: dict, action: str, observation: str) -> None:
    """Append a short action log entry to the session."""
    session["tool_history"].append({"action": action, "observation": observation})


def _wardrobe_compatibility_score(item: dict, wardrobe: dict) -> int:
    """
    Estimate how easy an item is to style with the user's wardrobe.

    This is intentionally simple: overlap in colors and style tags increases the
    score, and category diversity helps reward pairable items.
    """
    wardrobe_items = wardrobe.get("items", [])
    if not wardrobe_items:
        return 0

    item_colors = {color.lower() for color in item.get("colors", [])}
    item_tags = {tag.lower() for tag in item.get("style_tags", [])}
    item_category = item.get("category", "").lower()

    score = 0
    seen_categories = set()

    for wardrobe_item in wardrobe_items:
        wardrobe_colors = {
            color.lower() for color in wardrobe_item.get("colors", []) if color
        }
        wardrobe_tags = {
            tag.lower() for tag in wardrobe_item.get("style_tags", []) if tag
        }
        wardrobe_name = wardrobe_item.get("name", "").lower()
        wardrobe_category = wardrobe_item.get("category", "").lower()

        if item_colors & wardrobe_colors:
            score += 2
        if item_tags & wardrobe_tags:
            score += 3
        if wardrobe_category and wardrobe_category != item_category:
            score += 1
        if any(color in wardrobe_name for color in item_colors):
            score += 1
        if wardrobe_category:
            seen_categories.add(wardrobe_category)

    if len(seen_categories) >= 2:
        score += 2

    return score


def _select_best_result(results: list[dict], wardrobe: dict) -> dict:
    """Choose the best candidate from search results using simple reasoning."""

    def _rank(item_with_index: tuple[int, dict]) -> tuple[int, int, float]:
        index, item = item_with_index
        compatibility = _wardrobe_compatibility_score(item, wardrobe)
        search_rank_bonus = len(results) - index
        return (compatibility, search_rank_bonus, -item["price"])

    _, best_item = max(enumerate(results), key=_rank)
    return best_item


def _run_search_step(session: dict) -> None:
    """Search listings using the current constraints and store the observation."""
    constraints = session["current_constraints"]
    results = search_listings(
        constraints["description"],
        size=constraints["size"],
        max_price=constraints["max_price"],
        listings=session.get("listings"),
    )
    session["search_results"] = results
    session["search_attempts"].append(
        {
            "description": constraints["description"],
            "size": constraints["size"],
            "max_price": constraints["max_price"],
            "result_count": len(results),
        }
    )
    session["search_status"] = "results_found" if results else "no_results"
    _record_action(session, "search_listings", f"Found {len(results)} candidate items.")


def _relax_price_constraint(session: dict) -> None:
    """Drop the price filter and queue a new search."""
    max_price = session["current_constraints"]["max_price"]
    session["current_constraints"]["max_price"] = None
    session["relaxations"]["price"] = True
    session["search_status"] = "not_started"
    session["notes"].append(
        f"No results found under ${max_price:.2f}; removing the price filter and trying again."
    )
    _record_action(session, "relax_price", "Removed price constraint.")


def _relax_size_constraint(session: dict) -> None:
    """Drop the size filter and queue a new search."""
    size = session["current_constraints"]["size"]
    session["current_constraints"]["size"] = None
    session["relaxations"]["size"] = True
    session["search_status"] = "not_started"
    session["notes"].append(
        f"No results found for size '{size}'; removing the size filter and trying again."
    )
    _record_action(session, "relax_size", "Removed size constraint.")


def _valid_actions_for_state(session: dict) -> list[str]:
    """Return the valid next actions from the current session state."""
    if session["error"] or session["fit_card"]:
        return ["finish"]

    if not session["parsed"]:
        return ["parse_query"]

    if session["search_status"] == "not_started":
        return ["search"]

    if session["search_status"] == "no_results":
        actions = []
        if (
            session["current_constraints"].get("max_price") is not None
            and not session["relaxations"]["price"]
        ):
            actions.append("relax_price")
        if (
            session["current_constraints"].get("size") is not None
            and not session["relaxations"]["size"]
        ):
            actions.append("relax_size")
        actions.append("fail_no_results")
        return actions

    if session["search_results"] and session["selected_item"] is None:
        return ["select_item"]

    if session["selected_item"] and not session["outfit_suggestion"]:
        return ["suggest_outfit"]

    if session["outfit_suggestion"] and not session["fit_card"]:
        return ["create_fit_card"]

    return ["finish"]


def _fallback_next_action(session: dict, valid_actions: list[str] | None = None) -> str:
    """Choose the safest next action without using the planner."""
    valid_actions = valid_actions or _valid_actions_for_state(session)
    for action in _ACTION_PRIORITY:
        if action in valid_actions:
            return action
    return "finish"


_ALL_TOOL_DESCRIPTIONS = {
    "parse_query":    "extract description, size, and price from the user's natural language query",
    "search":         "search the listings catalog using current constraints",
    "relax_price":    "remove the price ceiling and allow a fresh search",
    "relax_size":     "remove the size filter and allow a fresh search",
    "select_item":    "pick the best matching listing scored by wardrobe compatibility",
    "suggest_outfit": "call the outfit LLM to style the item with the user's wardrobe",
    "create_fit_card":"call the fit card LLM to write a shareable social media caption",
    "fail_no_results":"terminate with an error — no results after all recovery attempts",
    "finish":         "end the session and return results to the user",
}


def _build_planner_prompt(session: dict, valid_actions: list[str]) -> str:
    """Create the planner prompt with goal, tools, workflow, progress, and state."""
    snapshot = {
        "query": session["query"],
        "current_constraints": session["current_constraints"],
        "search_status": session["search_status"],
        "search_attempts": session["search_attempts"],
        "relaxations_used": session["relaxations"],
        "result_count": len(session["search_results"]),
    }
    progress = {
        "query_parsed":     bool(session["parsed"]),
        "item_selected":    session["selected_item"]["title"] if session["selected_item"] else False,
        "outfit_suggested": bool(session["outfit_suggestion"]),
        "fit_card_created": bool(session["fit_card"]),
    }
    all_tools = "\n".join(
        f"  - {name}: {desc}" for name, desc in _ALL_TOOL_DESCRIPTIONS.items()
    )
    valid_tools = "\n".join(
        f"  - {a}: {_ALL_TOOL_DESCRIPTIONS.get(a, '')}" for a in valid_actions
    )
    return (
        "You are the decision-making planner for FitFinder, a fashion shopping agent.\n\n"
        "GOAL:\n"
        "  Help the user find a secondhand item matching their query, style it into a complete\n"
        "  outfit using their wardrobe, then produce a shareable fit card caption.\n\n"
        "ALL AVAILABLE TOOLS:\n"
        f"{all_tools}\n\n"
        "IDEAL WORKFLOW:\n"
        "  parse_query → search → [relax_price / relax_size if needed] →\n"
        "  select_item → suggest_outfit → create_fit_card → finish\n\n"
        "PROGRESS SO FAR:\n"
        f"{json.dumps(progress, indent=2)}\n\n"
        "DECISION RULES:\n"
        "  1. Prefer recovery over failure — only choose fail_no_results if nothing else is left.\n"
        "  2. When both relax_price and relax_size are available, relax_price first.\n"
        "     Exception: if max_price > $50, relax_size first instead.\n"
        "  3. After selecting an item, call suggest_outfit to give the user styling context.\n"
        "  4. After suggesting an outfit, call create_fit_card to complete the experience.\n"
        "  5. Only choose finish early if the user's goal is already fully met.\n\n"
        "ALLOWED ACTIONS RIGHT NOW (choose exactly one):\n"
        f"{valid_tools}\n\n"
        "Respond with valid JSON only — no text outside the object:\n"
        '{"action": "<chosen action>", "reason": "<one sentence explaining why>"}\n\n'
        f"Current state:\n{json.dumps(snapshot, indent=2)}"
    )


def _parse_planner_response(raw_content: str) -> dict:
    """Parse a JSON action object from the planner response."""
    raw_content = (raw_content or "").strip()
    if not raw_content:
        raise ValueError("Planner returned an empty response.")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if not match:
            raise ValueError("Planner response did not include JSON.") from None
        return json.loads(match.group(0))


def _query_planner_decision(session: dict, valid_actions: list[str]) -> tuple[str, str, str]:
    """Ask the LLM planner for the next action."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=_PLANNER_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a planning model for FitFinder, a fashion shopping agent. "
                    "You receive the agent's goal, all available tools, current progress, "
                    "and a constrained list of allowed actions for this step. "
                    "Return only a valid JSON object with exactly two keys: "
                    "'action' (must be from the allowed list) and "
                    "'reason' (one clear sentence explaining why this action moves the agent toward its goal). "
                    "Never include any text outside the JSON object."
                ),
            },
            {"role": "user", "content": _build_planner_prompt(session, valid_actions)},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    raw_content = response.choices[0].message.content
    payload = _parse_planner_response(raw_content)
    action = payload.get("action")
    reason = payload.get("reason", "")
    if action not in valid_actions:
        raise ValueError(f"Planner chose invalid action: {action}")
    return action, reason, raw_content


def _plan_next_action(session: dict) -> str:
    """Choose the next action, using the LLM planner when there is a real branch."""
    valid_actions = _valid_actions_for_state(session)
    fallback_action = _fallback_next_action(session, valid_actions)

    if len(valid_actions) == 1:
        session["planner_history"].append(
            {
                "source": "deterministic",
                "action": fallback_action,
                "reason": "Only one valid action was available.",
            }
        )
        return fallback_action

    try:
        action, reason, raw_content = _query_planner_decision(session, valid_actions)
        session["planner_history"].append(
            {
                "source": "llm",
                "action": action,
                "reason": reason,
                "raw": raw_content,
            }
        )
        return action
    except Exception as exc:  # noqa: BLE001
        session["planner_history"].append(
            {
                "source": "fallback",
                "action": fallback_action,
                "reason": f"Planner unavailable or invalid: {exc}",
            }
        )
        return fallback_action


def iter_agent(query: str, wardrobe: dict, listings: list | None = None):
    """
    Generator version of the agent loop. Yields a step-info dict after each
    action so callers can stream decisions in real time. The final session is
    always accessible from the last yielded value's "session" key.
    """
    session = _new_session(query, wardrobe, listings=listings)
    max_steps = 10

    print(f"\n[agent] Starting query: {query!r}")

    for step in range(max_steps):
        action = _plan_next_action(session)

        planner_entry = session["planner_history"][-1] if session["planner_history"] else {}
        source = planner_entry.get("source", "")
        reason = planner_entry.get("reason", "")
        source_label = f"[{source}]" if source else ""
        print(f"[agent] step {step + 1}: {action} {source_label}  {reason}")

        if action == "finish":
            break

        if action == "parse_query":
            parsed = _parse_query(query)
            session["parsed"] = parsed
            session["current_constraints"] = parsed.copy()
            _record_action(
                session,
                "parse_query",
                (
                    "Parsed query into description="
                    f"'{parsed['description']}', size={parsed['size']}, "
                    f"max_price={parsed['max_price']}"
                ),
            )

        elif action == "search":
            _run_search_step(session)

        elif action == "relax_price":
            _relax_price_constraint(session)

        elif action == "relax_size":
            _relax_size_constraint(session)

        elif action == "fail_no_results":
            session["error"] = (
                "No listings found even after relaxing the available filters. "
                "Try different keywords or broaden your search."
            )
            _record_action(session, "fail_no_results", session["error"])

        elif action == "select_item":
            session["selected_item"] = _select_best_result(
                session["search_results"], wardrobe
            )
            _record_action(
                session,
                "select_item",
                f"Selected '{session['selected_item']['title']}' from candidates.",
            )

        elif action == "suggest_outfit":
            outfit = suggest_outfit(session["selected_item"], wardrobe)
            if not outfit or not outfit.strip():
                session["error"] = "Unable to generate an outfit suggestion."
                _record_action(session, "suggest_outfit", session["error"])
            else:
                session["outfit_suggestion"] = outfit
                _record_action(session, "suggest_outfit", "Generated outfit suggestion.")

        elif action == "create_fit_card":
            fit_card = create_fit_card(
                session["outfit_suggestion"], session["selected_item"]
            )
            if not fit_card or not fit_card.strip() or fit_card.startswith("Error:"):
                session["error"] = fit_card or "Unable to create a fit card."
                session["fit_card"] = None
                _record_action(session, "create_fit_card", session["error"])
            else:
                session["fit_card"] = fit_card
                _record_action(session, "create_fit_card", "Created fit card.")

        else:
            session["error"] = f"Agent entered an unknown action state: {action}"
            _record_action(session, "unknown_action", session["error"])

        observation = session["tool_history"][-1]["observation"] if session["tool_history"] else ""
        print(f"         -> {observation}")

        if source == "llm":
            explanation = reason
        else:
            explanation = _DETERMINISTIC_EXPLANATIONS.get(action, observation)

        yield {
            "step": step + 1,
            "action": action,
            "source": source,
            "reason": reason,
            "explanation": explanation,
            "observation": observation,
            "session": session,
        }

        if session["error"]:
            break

    if not session["error"] and not session["fit_card"]:
        session["error"] = "Agent stopped before completing the request."
        _record_action(session, "timeout", session["error"])


def run_agent(query: str, wardrobe: dict, listings: list | None = None) -> dict:
    """Run the agent loop and return the final session dict."""
    session = None
    for step in iter_agent(query, wardrobe, listings=listings):
        session = step["session"]
    return session


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    demo_session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    print(demo_session)
