"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex. The remainder after stripping size/price tokens becomes the
    description keyword string passed to search_listings().

    Handles patterns like:
      "vintage graphic tee under $30, size M"
      "90s track jacket in size M"
      "black combat boots size 8"
    """
    text = query

    # Price: "under $30", "below $25", "for $20", or bare "$30"
    max_price = None
    price_match = re.search(
        r"(?:under|below|max|for)\s+\$(\d+(?:\.\d+)?)", text, re.IGNORECASE
    )
    if not price_match:
        price_match = re.search(r"\$(\d+(?:\.\d+)?)", text)
    if price_match:
        max_price = float(price_match.group(1))
        text = text[: price_match.start()] + text[price_match.end() :]

    # Size: "size M", "size XL", "size 8", "size S/M"
    size = None
    size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)", text, re.IGNORECASE)
    if size_match:
        size = size_match.group(1)
        text = text[: size_match.start()] + text[size_match.end() :]

    # Description is everything that remains, whitespace-normalized
    description = re.sub(r"\s+", " ", text).strip().strip(",").strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: first reduce the scope of the constraints by first removing 
                the max price constraint and rerunning search_listings() and then 
                removing the size constraint and rerunning search_listings(), with 
                every constraint relaxation resulting in sending a message to the user 
                which constraint has been relaxed. If there are still no results from the end 
                of these relaxations,               
                set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)
    session["notes"] = []  # informational messages about constraint relaxation

    # Step 2: Parse query into structured parameters
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3: Search with full constraints, relaxing one at a time if needed
    results = search_listings(description, size=size, max_price=max_price)
    print(f'search results: {session["search_results"]}')

    if not results and max_price is not None:
        session["notes"].append(
            f"No results found under ${max_price:.2f} — removing price filter and trying again."
        )
        results = search_listings(description, size=size, max_price=None)
        print(f'search results after missing 1: {session["search_results"]}')

    if not results and size is not None:
        session["notes"].append(
            f"No results found for size '{size}' — removing size filter and trying again."
        )
        results = search_listings(description, size=None, max_price=None)
        print(f'search results after missing 2: {session["search_results"]}')

    if not results:
        session["error"] = (
            "No listings found even after relaxing price and size filters. "
            "Try different keywords or broaden your search."
        )
        return session
    


    session["search_results"] = results


    # Step 4: Pick the top result
    session["selected_item"] = results[0]
    print(f'selected item: {session["selected_item"]}')
    print(f'search results: {session["search_results"]}')

    # Step 5: Suggest outfit using the top listing and the user's wardrobe
    session["outfit_suggestion"] = suggest_outfit(results[0], wardrobe)
    print(f'outfit suggestions: {session["outfit_suggestion"]}')

    # Step 6: Generate the shareable fit card caption
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], results[0])
    print(f'fit_card: {session["fit_card"]}')


    # Step 7: Return the completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    #print(f"{session2['fit_card']}")
