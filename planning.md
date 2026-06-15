# FitFindr — planning.md

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

If Nothing matches, Do not raise an execption. Instead, loosen the constraints by first removing the max_price constraint and requerying, explaining to the user what was adjusted.

Then it should loosen the size constraint and then requery. If no items survive both, then FitFindr tells the user what to try differently and stops

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

- `outfit` (...): The outfit suggestion string from suggest_outfit().
- `new_item`: The listing dict for the thrifted item. Top choice should be at index 0

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

For each 3 tools, I will give claude the relevent tool specs and the planning.md as context to inform its initial tool construction. I will also make sure that each tool uses the required helper functions (such as load_listings() for the search listings tool). Then, I will have it generate a test suite, where I will then check for if it passes the suite and then prove 3 test queries as a form of quality control.

**Milestone 4 — Planning loop and state management:**
For the planning loop and state management, I will give claude the planning.md, the flow diagram, and tool specificiations (like search_listings() for example)

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

FitFindr needs to take a shopper's request, find the best matching item from the listings dataset, and filter out items when they don't meet the constraints, like price or size. After the agent chooses a good match, it should use the user’s wardrobe to suggest how to style the piece and then generate a “fit card” caption that sumerizes up the look.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**

The agent will go set everything up by parsing the user query and filling the subsequent fields of desc, size, and max price, and then and call search_listings with the resulting description of "vintage graphic tee under $30", Size being None, and the max price being 30.

<!-- What does the agent do first? Which tool is called? With what input? -->

**Step 2:**

They return a json list from data/listings.json with everything that fits the criteria ordered by relevency. Then, they store those results. Next, they will call the suggest_outfit() function with new item being the top item from the json list, containing these fields:

id, title, "vintage graphic tee under $30", category, style_tags (list), None,
condition, 30 (float), colors (list), brand, platform

and the wardrobe being the wardrobe from the session.

Then, it will send it to an LLM to determine what is the best fitting one.

<!-- What happens next? What was returned from step 1? What tool is called now? -->

**Step 3:**

The agent will then store the resulting suggestion from the suggest_outfit function, and then put in the new item found and the new outfit suggestoin to create a social media caption.

<!-- Continue until the full interaction is complete -->

**Final output to user:**

The Handel_query function finally returns out the listing_text, outfit_suggestion, and Fit_card. finally, the user sees all 3 in seperate fields.
