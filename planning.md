# Fit Finder — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**

This tool should search the listings dataset in listings.json and find items matching the description, size and price ceiling.
Description matching should be based upon keyword similiarity.

**Input parameters:**

- `description` (str): It should be Keywords describing what the user is looking for
- `size` (str): Size string to filter items (Ie M, m, S). It is case insensitive. If none, then there is no size constraint
- `max_price` (float): Maximum price (inclusive). If None, there is no price constraint either

**What it returns:**

It should return a list of matching listing dicts, sorted by relevance (best match first). Relevence is decided first by fitting the nessacary constraints of size and price and then keyword matching with the decription by the user. Score the surviving listings through keyword overlap with the description, and drop all items with score 0. Finally, Sort all the resulting listings by score, highest first, and return the listing dicts.

Each listing dict has the following fields:
id, title, description, category, style_tags (list), size,
condition, price (float), colors (list), brand, platform

**What happens if it fails or returns nothing:**

If Nothing matches, Do not raise an execption. Instead, loosen the constraints by first removing the max_price constraint and requerying, explaining to the user what was adjusted. this loosening will be
organized/orchestrated by agent.py rather than in this specific tool.

Then it should loosen the size constraint and then requery. If no items survive both, then Fit Finder tells the user what to try differently and stops

---

### Tool 2: suggest_outfit

**What it does:**

Given a thrifted item and the user's wardrobe, suggests 1–2 complete outfits using groq.

**Input parameters:**

- `new_item` (dict): the item the user is considering buying (top item is at index 0)
- `wardrobe` (dict): A wardrobe dict with an 'items' key containing a list of wardrobe item dicts. Note that this may be empty

**What it returns:**

A non-empty string with outfit suggestions.
If the wardrobe is empty, offer general styling advice for the item
rather than raising an exception or returning an empty string.

**What happens if it fails or returns nothing:**

If the wardrobe is empty, call the LLM with a prompt for general styling ideas
(what kinds of items pair well, what vibe it suits, etc.).

---

### Tool 3: create_fit_card

**What it does:**

Create a short, shareable outfit caption (instagram like) for the thrifted find.

**Input parameters:**

- `outfit` (str): The outfit suggestion string from suggest_outfit().
- `new_item` (dict): The listing dict for the thrifted item. Top choice should be at index 0

**What it returns:**

A 2–4 sentence string usable as an Instagram/TikTok caption.

        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

The caption should: - Feel casual and authentic (like a real OOTD post, not a product description) - Mention the item name, price, and platform naturally (once each) - Capture the outfit vibe in specific terms - Sound different each time for different inputs (use higher LLM temperature)

**What happens if it fails or returns nothing:**

If outfit string is empty or whitespace, send a descriptive error message string

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The agent will first parse the user's query into a description, size, and max price and then call search_listings with those values. If the search listings are empty, then the agent errors and does not immediately contintue to the next step.

If the first search returns nothing, it retrys by loosening constraints (first by removing the price filter and then by removing the size filter). The loosening constraints only happen if the first search returns nothing, as restraints are kept so long as there are valid wardrobe solutions. Should there still be no matches after the retries, the agent stops early, stores an error message, and then returns.

When there is a valid first search result, the agent then saves the resulting matching dicts in the session state. Then, it will pick the top result (results[0]) and store that as the selected_item, and call suggest_outfit() with that selected item and the users wardrobe. At this point, the loop is looking at search results and using the best one to decide the next tool call.

If the user's wardrobe is empty (wardrobe), then the LLM should return general styling advice instead. If not, the LLM will suggest 1-2 complete outfits using groq.

Finally, the agent will store the output into the outfit suggestion field and passes both the outfit suggestion field and the new item to the create_fit_card().

If the outfit suggestion field is blank, send a descriptive error message. If not, then create a 2-4 sentence caption.

Finally, the agent will fill out the fit card and then return it. The planning loop knows when it is done when it either has stored an error and returned early, or it has stored the fit_card and returned correctly.

<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

---

## State Management

**How does information from one tool get passed to the next?**

The agent uses a session dictionary as the ground truth. The session stores the origional query, parsed inputs, search results, selected listing, wardrobe being used, outfit suggestion, the final fit card, and any error messages.

Data is tracked through the session dictionary, as each tool reads the inputs it needs from the session and writes the output back into the session. Data is passed between tool calls by saving all outputs into the session dictionary and then using that value for the next tool

<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool            | Failure mode                          | Agent response                                                          |
| --------------- | ------------------------------------- | ----------------------------------------------------------------------- |
| search_listings | No results match the query            | First, reduce the constraints, and if nothing is still there then error |
| suggest_outfit  | Wardrobe is empty                     | call the LLM with a prompt for general styling ideas                    |
| create_fit_card | Outfit input is missing or incomplete | return an error message string                                          |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

User query
│
▼
Planning Loop
│
├─► Initialize session
│ Session:
│ - query = user query
│ - parsed = {}
│ - search_results = []
│ - selected_item = None
│ - outfit_suggestion = None
│ - fit_card = None
│ - error = None
│
├─► Parse query
│ Session:
│ - parsed["description"] = ...
│ - parsed["size"] = ...
│ - parsed["max_price"] = ...
│
├─► search_listings(description, size, max_price)
│ │
│ ├─► results = [item, ...]
│ │ Session:
│ │ - search_results = results
│ │ - selected_item = results[0]
│ │
│ └─► results = []
│ │
│ ├─► Retry without max_price
│ │ search_listings(description, size, None)
│ │ │
│ │ ├─► results = [item, ...]
│ │ │ Session:
│ │ │ - search_results = results
│ │ │ - selected_item = results[0]
│ │ │
│ │ └─► results = []
│ │ │
│ │ ├─► Retry without size
│ │ │ search_listings(description, None, None)
│ │ │ │
│ │ │ ├─► results = [item, ...]
│ │ │ │ Session:
│ │ │ │ - search_results = results
│ │ │ │ - selected_item = results[0]
│ │ │ │
│ │ │ └─► results = []
│ │ │ Session:
│ │ │ - error = "No listings found, even after relaxing price and size filters."
│ │ │ ▼
│ │ │ Return session
│
├─► suggest_outfit(selected_item, wardrobe)
│ │
│ ├─► wardrobe empty
│ │ Return general styling advice
│ │
│ └─► wardrobe has items
│ Return specific outfit suggestions
│
│ Session:
│ - outfit_suggestion = "..."
│
├─► create_fit_card(outfit_suggestion, selected_item)
│ │
│ ├─► outfit missing/incomplete
│ │ Return error message string
│ │
│ └─► outfit valid
│ Return caption
│
│ Session:
│ - fit_card = "..."
│
▼
Return session

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

For search_listings: I will give Claude the Tool 1 "Input parameters," "What it returns," and "What happens if it fails or returns nothing" sections, plus the note that it must use load_listings() from utils/data_loader.py. I will ask it to implement keyword scoring without calling an LLM. I will verify by running 3 manual queries: a matching query (returned sorted results), a price-filtered query (items above the cap excluded), and a zero-match query (returned [] without raising).

For suggest_outfit: I will give Claude the Tool 2 "Input parameters," "What it returns," and "What happens if it fails or returns nothing" sections. I will specifically highlight the empty-wardrobe case requiring a fallback LLM prompt. I will verify by calling it with get_empty_wardrobe() and confirming the response is a non-empty styling string, not an exception.

For create_fit_card: I will give Claude the Tool 3 "Input parameters," "What it returns," and "What happens if it fails or returns nothing" sections, including the requirement to return a descriptive error string (not raise) when outfit is empty or whitespace. I will verify by calling create_fit_card('', sample_listing) and confirming the returned string contains a descriptive error message.

In addition to all of this, I will ask Claude to generate a test suite for more in-depth testing.

**Milestone 4 — Planning loop and state management:**

I will give Claude the Planning Loop section, the State Management section, and the Architecture diagram (the full ASCII flowchart). I will ask it to implement run_agent() so that state will pass only through the session dict and constraint relaxation messages will be stored in session["notes"]. I will verify by running both the happy-path query and the zero-match ballgown query, checking that the session dict will contain the correct fields and that session["error"] will be None on success and populated on failure.

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

Fit Finder needs to take a shopper's request, find the best matching item from the listings dataset, and filter out items when they don't meet the constraints, like price or size. After the agent chooses a good match, it should use the user’s wardrobe to suggest how to style the piece and then generate a “fit card” caption that sumerizes up the look.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**

The agent will go set everything up by parsing the user query and filling the subsequent fields of desc, size, and max price, and then and call search_listings() with the resulting description of "vintage graphic tee under $30", Size being None, and the max price being 30.

**Step 2:**

Search_listings Then returns a list of listing dicts from `data/listings.json`, sorted by keyword relevance. For this query the top result is a listing whose fields come from the dataset — for example:

{
"id": "lst_002",
"title": "Y2K Baby Tee — Butterfly Print",
"description": "Super cute early 2000s baby tee with butterfly graphic",
"category": "tops",
"style_tags": ["y2k"],
"size": "S/M",
"condition": "excellent",
"price": 18.0,
"colors": ["white"],
"brand": null,
"platform": "depop"
}

The agent stores this list in session["search_results"] and sets session["selected_item"] to results[0]. It then calls suggest_outfit(session["selected_item"], session["wardrobe"]). The LLM receives the item's title, description, style tags, and the user's existing wardrobe items to generate 1–2 outfit suggestions.

**Step 3:**

The agent stores the suggestion string into session["outfit_suggestion"]. Because we now have both a confirmed item and a complete outfit suggestion, the agent calls create_fit_card(session["outfit_suggestion"], session["selected_item"]) to generate a shareable caption. The outfit string is passed first (as required by the function signature), followed by the listing dict so the caption can reference the item's title, price, and platform.

<!-- Continue until the full interaction is complete -->

**Final output to user:**

run_agent() returns the completed session dict. The caller can then display session["selected_item"]["title"], session["outfit_suggestion"], and session["fit_card"] as separate fields: the listing found, how to style it, and the shareable caption.
