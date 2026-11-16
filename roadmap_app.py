"""Standalone roadmap form. Launch with: streamlit run roadmap_app.py."""

import logging

import streamlit as st

from src.agent.learning_purpose import PURPOSE_LABELS
from standalone_roadmap.service import (
    MAX_BACKGROUND_CHARACTERS,
    MAX_GOAL_CHARACTERS,
    RoadmapGenerationError,
    RoadmapUnavailableError,
    generate_roadmap,
)


def main() -> None:
    """Generate only on form submission; retain the result across reruns."""
    # Provide console output when the host has no logging handler configured.
    logging.basicConfig(format="%(levelname)s %(name)s %(message)s")
    st.title("Roadmap Generator")
    with st.form("roadmap_form"):
        goal = st.text_area("Learning goal (required)", max_chars=MAX_GOAL_CHARACTERS)
        background = st.text_area(
            "Current background/skills (optional)", max_chars=MAX_BACKGROUND_CHARACTERS,
        )
        purpose = st.selectbox(
            "Learning purpose",
            ["career_development", "topic_mastery", "certification_preparation"],
            format_func=PURPOSE_LABELS.get,
        )
        hours = st.number_input(
            "Available weekly learning hours", min_value=0.5, max_value=10.0,
            value=2.0, step=0.5,
        )
        intensity = st.selectbox("Learning intensity", ["light", "medium", "hardcore"], index=1)
        submitted = st.form_submit_button("Generate roadmap")

    if submitted:
        try:
            with st.spinner("Generating roadmap…"):
                st.session_state["roadmap_markdown"] = generate_roadmap(
                    goal=goal, background=background, learning_purpose=purpose,
                    hours_per_week=hours, learning_intensity=intensity,
                )
        except RoadmapUnavailableError as exc:
            # A refused request keeps the existing result available to download.
            st.error(str(exc))
        except ValueError as exc:
            st.session_state.pop("roadmap_markdown", None)
            st.error(f"Please check your learner inputs: {exc}")
        except RoadmapGenerationError as exc:
            st.session_state.pop("roadmap_markdown", None)
            st.error(str(exc))

    if "roadmap_markdown" in st.session_state:
        markdown = st.session_state["roadmap_markdown"]
        st.markdown(markdown)
        st.download_button(
            "Download roadmap as Markdown", data=markdown,
            file_name="learning-roadmap.md", mime="text/markdown",
            on_click="ignore",
        )


if __name__ == "__main__":
    main()
