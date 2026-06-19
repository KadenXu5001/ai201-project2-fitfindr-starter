"""
app.py

Gradio interface for Fit Finder. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import iter_agent
from utils.data_loader import get_demo_wardrobe, get_example_wardrobe, get_empty_wardrobe, load_demo_listings


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str):
    """
    Generator called by Gradio when the user submits a query. Yields
    (listing_text, outfit_suggestion, fit_card, dashboard) tuples so the
    agent decision dashboard streams in real time as the agent runs.
    """
    if not user_query or not user_query.strip():
        yield "Please enter a search query.", "", "", ""
        return

    if wardrobe_choice == "Example wardrobe":
        wardrobe = get_example_wardrobe()
    elif wardrobe_choice == "Demo wardrobe (constraint relaxation)":
        wardrobe = get_demo_wardrobe()
    else:
        wardrobe = get_empty_wardrobe()

    listings = load_demo_listings() if wardrobe_choice == "Demo wardrobe (constraint relaxation)" else None

    decisions = []
    session = None

    for step in iter_agent(user_query, wardrobe, listings=listings):
        session = step["session"]
        entry = f"Step {step['step']}: selected {step['action']} tool"
        if step["observation"]:
            entry += f"\n  → {step['observation']}"
        decisions.append(entry)
        yield "", "", "", "\n\n".join(decisions)

    if session is None:
        yield "No response from agent.", "", "", ""
        return

    if session["error"]:
        notes = "\n".join(session.get("notes", []))
        error_text = (notes + "\n\n" + session["error"]).strip()
        yield error_text, "", "", "\n\n".join(decisions)
        return

    item = session["selected_item"]
    notes = session.get("notes", [])

    listing_lines = [
        item["title"],
        f"Price: ${item['price']:.2f}  |  Size: {item['size']}  |  Condition: {item['condition']}",
        f"Platform: {item['platform']}",
        f"Style: {', '.join(item['style_tags'])}",
        f"Colors: {', '.join(item['colors'])}",
    ]
    if item.get("brand"):
        listing_lines.append(f"Brand: {item['brand']}")
    listing_lines += ["", item["description"]]

    listing_text = "\n".join(listing_lines)
    if notes:
        listing_text = "\n".join(notes) + "\n\n" + listing_text

    yield listing_text, session["outfit_suggestion"], session["fit_card"], "\n\n".join(decisions)


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",
]

DEMO_QUERIES = [
    "brown hoodie under $50 size M",
    "green jacket under $15 size M",
    "black jeans under $20 size L",
]

def build_interface():
    with gr.Blocks(title="Fit Finder") as demo:
        gr.Markdown("""
# Fit Finder 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            with gr.Column(scale=3):
                with gr.Row():
                    query_input = gr.Textbox(
                        label="What are you looking for?",
                        placeholder="e.g. vintage graphic tee under $30, size M",
                        lines=2,
                        scale=3,
                    )
                    wardrobe_choice = gr.Radio(
                        choices=["Example wardrobe", "Demo wardrobe (constraint relaxation)", "Empty wardrobe (new user)"],
                        value="Example wardrobe",
                        label="Wardrobe",
                        scale=1,
                    )

                submit_btn = gr.Button("Find it", variant="primary")

                with gr.Row():
                    listing_output = gr.Textbox(
                        label="🛍️ Top listing found",
                        lines=10,
                        interactive=False,
                    )
                    outfit_output = gr.Textbox(
                        label="👗 Outfit idea",
                        lines=10,
                        interactive=False,
                    )
                    fitcard_output = gr.Textbox(
                        label="✨ Your fit card",
                        lines=10,
                        interactive=False,
                    )

                gr.Examples(
                    examples=[
                        *[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
                        *[[q, "Demo wardrobe (constraint relaxation)"] for q in DEMO_QUERIES],
                    ],
                    inputs=[query_input, wardrobe_choice],
                    label="Try these queries",
                )

            with gr.Column(scale=1, min_width=260):
                dashboard_output = gr.Textbox(
                    label="🤖 Agent decisions",
                    lines=28,
                    interactive=False,
                )

        outputs = [listing_output, outfit_output, fitcard_output, dashboard_output]

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
            show_progress="hidden",
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=outputs,
            show_progress="hidden",
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
