"""Standalone roadmap form. Launch with: streamlit run roadmap_app.py."""

import streamlit as st

from src.agent.learning_purpose import PURPOSE_LABELS
from standalone_roadmap.service import RoadmapGenerationError, generate_roadmap


def main() -> None:
    """Generate only on form submission; retain the result across reruns."""
    st.title("Roadmap Generator")
    with st.form("roadmap_form"):
        goal = st.text_area("Learning goal (required)")
        background = st.text_area("Current background/skills (optional)")
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
        # Clear the previous result so a failed new request cannot show stale output.
        st.session_state.pop("roadmap_markdown", None)
        try:
            with st.spinner("Generating roadmap…"):
                st.session_state["roadmap_markdown"] = generate_roadmap(
                    goal=goal, background=background, learning_purpose=purpose,
                    hours_per_week=hours, learning_intensity=intensity,
                )
        except ValueError as exc:
            st.error(f"Please check your learner inputs: {exc}")
        except RoadmapGenerationError as exc:
            st.error(str(exc))

    if "roadmap_markdown" in st.session_state:
        st.markdown(st.session_state["roadmap_markdown"])


if __name__ == "__main__":
    main()
