# Standalone Roadmap Generator

Run these commands from the repository root using Python 3.10 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If you already have the repository's virtual environment, activate it and install
the requirements without recreating it.

The server requires `OPENAI_API_KEY` in its environment. In Bash, enter it at a
hidden prompt so it is not included in the command or shell history:

```bash
read -r -s -p "OpenAI API key: " OPENAI_API_KEY
export OPENAI_API_KEY
printf '\n'
python -m streamlit run roadmap_app.py
```

Open the local URL printed by Streamlit. Fill in the learner form and select
**Generate roadmap**. Generation makes a paid API request using the server's
configured model. API keys stay on the server; do not put them in source files.

Select **Download roadmap as Markdown** to download the displayed roadmap as
`learning-roadmap.md`. Downloading makes no additional generation request.
Results are held only in the current Streamlit session; the application does not
save roadmap files or maintain history.
