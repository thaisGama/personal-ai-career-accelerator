# Standalone Roadmap Generator

Run these commands from the repository root using Python 3.10 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If you already have the repository's virtual environment, activate it and install
the requirements without recreating it.

For local development, use a key from a dedicated development OpenAI project.
The server requires `OPENAI_API_KEY` in its environment. In Bash, enter it at a
hidden prompt so it is not included in the command or shell history:

```bash
read -r -s -p "OpenAI API key: " OPENAI_API_KEY
export OPENAI_API_KEY
export ROADMAP_ENVIRONMENT="development"
export ROADMAP_GENERATION_ENABLED="true"
export ROADMAP_DAILY_LIMIT="0"
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

## Environment configuration and usage protection

Both environments run the same `roadmap_app.py`. Standalone settings live in
`standalone_roadmap/config.py` and are read from environment variables on each
valid generation submission. Invalid settings disable new generation with a safe
message; they never fall back to unlimited use. No credentials are stored in code.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | Required when enabled | Key belonging to the OpenAI project for this environment. Missing/blank keys block generation before admission. |
| `ROADMAP_ENVIRONMENT` | `beta` | `development`, `beta`, or `production`. Production uses beta safeguards. Set development explicitly for local work. |
| `ROADMAP_GENERATION_ENABLED` | `true` | `true` or `false` only; `false` rejects new attempts and keeps existing session roadmaps/downloads. |
| `ROADMAP_DAILY_LIMIT` | Development: `0`; beta/production: `10` | Maximum admitted attempts per UTC day. Development allows `0` (unlimited) or a positive integer. Beta/production allows only `1`–`10`; use the kill switch to stop all generation. |

All modes allow **one active standalone generation per process**. The individual
2,000/6,000-character input limits, 120-second API timeout, 8,000-token output
ceiling, and zero retries remain in effect. These server-owned defaults are
centralized alongside the environment settings; the existing `timeout_seconds`
service argument remains available to server callers. No new settings affect the
original Career Accelerator or the standalone prompt-inspection CLI.

Use a different OpenAI project/key for the hosted beta, keeping development and
tester usage separate. The app uses the project associated with the supplied key;
there is no automatic project creation or project switching. In Streamlit
Community Cloud, supply the following **root-level string values** through the
app's Secrets settings (replace the placeholder privately). Streamlit exposes
root-level secrets as environment variables, so the application reads the same
settings in both environments. See [Streamlit secrets management](https://docs.streamlit.io/develop/concepts/connections/secrets-management)
and [Community Cloud secrets settings](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).

```toml
OPENAI_API_KEY = "REPLACE_WITH_BETA_PROJECT_KEY"
ROADMAP_ENVIRONMENT = "beta"
ROADMAP_GENERATION_ENABLED = "true"
ROADMAP_DAILY_LIMIT = "10"
```

Keep real keys out of the repository, browser inputs, and logs. `.env` and
`.streamlit/secrets.toml` are ignored. The standalone app does not automatically
load `.env`; export its settings before starting Streamlit if you use one.

One thread-safe, module-level admission controller shares the allowance across
all Streamlit sessions in the **same Python process**. It atomically checks the
kill switch, active generation, and daily allowance before admitting an attempt.
An admitted attempt counts even if the API fails or returns invalid output.
Busy, disabled, invalid-input, invalid-configuration, and exhausted-quota requests
make no API call and consume no allowance. Form edits, downloads, and ordinary
reruns also consume nothing. A busy request is rejected immediately; there is no
queue or automatic retry. Capacity is released after completion or failure.

The allowance resets at **00:00 UTC**, on the next admission check. An attempt
belongs to the day it was admitted; crossing midnight never releases an active
generation. Settings changes do not themselves reset the counters. To stop new
generations, set `ROADMAP_GENERATION_ENABLED="false"` on the server (or the
equivalent string in hosted Secrets). Existing in-flight work can finish; this
switch does not cancel requests. Previously generated session results remain
available after an admission refusal. The app reads current environment settings
on subsequent submissions; changing deployment secrets may require a restart.

**This is not a hard spending cap.** Counters are in memory and reset whenever
the Python process restarts, sleeps and restarts, or is replaced. Multiple
processes or replicas each have their own allowance. Other applications or
direct API calls using the key bypass this controller, and each allowed request
has variable token usage. OpenAI project budget alerts are notifications, not
guaranteed spending ceilings; [official OpenAI documentation](https://developers.openai.com/api/docs/guides/terraform/rate-limits-and-spend#configure-a-project-spend-alert)
explicitly distinguishes spend alerts from hard limits. Monitor the dedicated
beta project's usage and use the kill switch when needed. This slice assumes a
single hosted process and does not enforce a durable daily allowance.
