# Fit Finder — README.md

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
- `new_item`(dict): The listing dict for the thrifted item. Top choice should be at index 0

**What it returns:**

A 2–4 sentence string usable as an Instagram/TikTok caption.

        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

The caption should: - Feel casual and authentic (like a real OOTD post, not a product description) - Mention the item name, price, and platform naturally (once each) - Capture the outfit vibe in specific terms - Sound different each time for different inputs (use higher LLM temperature)

**What happens if it fails or returns nothing:**

If outfit string is empty or whitespace, send a descriptive error message string

---

### Additional Tools (if any)

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

---

## State Management

**How does information from one tool get passed to the next?**

The agent uses a session dictionary as the ground truth. The session stores the origional query, parsed inputs, search results, selected listing, wardrobe being used, outfit suggestion, the final fit card, and any error messages.

Data is tracked through the session dictionary, as each tool reads the inputs it needs from the session and writes the output back into the session. Data is passed between tool calls by saving all outputs into the session dictionary and then using that value for the next tool

---

## Error Handling

Error handling strategy for each tool, with concrete examples from testing:

- `search_listings`: If no listings match the query, the tool returns an empty list instead of raising an exception. Then the agent handles recovery by relaxing constraints one at a time, first removing the price ceiling and then the size filter. If there are still no matches, the agent stops early and stores a helpful error message for the user.

In testing, `search_listings('designer ballgown', size='XXS', max_price=5)` returned `[]`, which confirms the tool fails safely.

- `suggest_outfit`: If the wardrobe is empty, the tool does not fail or return a blank string. Instead, it calls the LLM with a fallback prompt that gives general styling advice for the thrifted item.

In testing, `suggest_outfit(results[0], get_empty_wardrobe())` returned a LLM generated response rather than a blank string.

- `create_fit_card`: If the outfit suggestion is missing, empty, or only whitespace, the tool returns a descriptive error string instead of raising an exception or calling the LLM. This prevents the agent from generating a caption from incomplete state.

In testing, `create_fit_card('', results[0])` returned `Error: Cannot generate a fit card — the outfit suggestion is missing or empty. Please call suggest_outfit() first and pass its result here.`

---

## Spec Reflection

I feel like one way the spec helped me was with the archetecture diagram.
I think that the design of the archetecture was quite helpful for me, since
without it, I probably wouldn't have been able to utilize the tools in the right place.
I would have probably made the retry logic for the loosening of search listings in search listings itself, which would have probably been a poorer implementation due to higher coupling. With the sepc though, I got a better understanding of compartimentalization.

One place that I deviated from the spec was with the initial archetecture loop, as I added loose additions and search listing reruns. Since I did the retry logic, Instead of exiting after a missed search listing, I had to implement a second & thrid round of search listings.

---

## AI Usage

**Instance 1**

- \_What I gave the AI: a task to create unit tests, supplimented with tools.py and planning.md
- \_What it produced: simple unit tests with out the correct specified failure mode logic for suggest outfit empty wardrobe advice
- \_What I changed or overrode: Manually tweaked prompt to include the missing empty wardrobe case.

**Instance 2**

- \_What I gave the AI: A task to create Search listings given the planning.md and tools.py
- \_What it produced: The exact ideas in tools.py, not taking into account the specific changes I had in mind for the tool in planning.md
- \_What I changed or overrode: Manually tweaked prompt to include relevence scoring by explicit keyword matching instead of calling groq.

---

## Community Choice

**r/nba** — one of Reddit's most active sports communities, with thousands of posts daily ranging from rigorous statistical breakdowns to pure emotional reactions. The discourse quality gap is wide and real: a post citing PER, true shooting %, and historical comparisons sits in a completely different category than "bro this take is cooked 💀". This variance makes r/nba a strong fit for a classification task — the labels are grounded in distinctions that community members themselves make constantly.
