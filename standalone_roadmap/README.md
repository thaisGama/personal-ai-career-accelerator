# Standalone Roadmap Generator

Run these commands from the repository root using Python 3.12 (tested locally on 3.12.3):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Runtime dependencies are pinned in `requirements.txt`: OpenAI SDK 2.9.0,
Streamlit 1.52.1, and python-dotenv 1.2.1. For development/tests, install
`python -m pip install -r requirements-dev.txt`, which also pins pytest 9.0.2.
These are direct dependency pins; transitive dependencies are resolved by pip.
The app's imported modules/templates are included in the repository; no external
system packages or generated roadmap files are needed for startup.

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


## Output validation and operational logs

The shared roadmap validator rejects boolean, nonfinite, zero, and negative
estimates. Each phase must match its milestone-hour sum, and total hours must
match the phase-hour sum, with an **absolute tolerance of 0.05 hours** (three
minutes) at each boundary. Week estimates for 2/5/7 hours per week must match
`total_estimated_hours / weekly_hours` within **0.05 weeks**, or equal that ratio
rounded upward to a whole week. For example, five hours accepts 2.5 or 3 weeks
at two hours/week, and 0.71 or 1 week at seven hours/week. Decimal arithmetic
keeps the tolerance boundaries explicit. There is no educational-duration cap.
Invalid output uses the existing safe error; it is never repaired or retried.

Each admitted attempt emits one INFO record through the standard Python logger
`standalone_roadmap.service`, with outcome, safe category, elapsed seconds,
configured model, and input/output token counts when available. Categories are
`none` (success), `api_timeout`, `api_failure`, `invalid_output`, and a fallback
`internal_error`. Missing counts are `None`. Logs omit learner fields, prompts,
responses, credentials, and exception text. Logging-handler failures do not
change results, capacity release, or allowance accounting. The shared API helper
retains its historical token print by default for existing callers; standalone
generation opts out with `log_usage=False` and emits its own terminal record.

## Streamlit Community Cloud deployment

1. Use repository `thaisGama/personal-ai-career-accelerator`. After collaborative
   review and approval, merge the hardening changes into the release branch
   `master`; select that branch for deployment and record its approved commit SHA.
   The preparation branch is `feature/roadmap-request-limits`. Do not deploy an
   older `master` revision or assume uncommitted local work is available to Cloud.
2. In Community Cloud, choose **Create app**, select that repository/release
   branch, and set the entrypoint to **`roadmap_app.py`** at the repository root.
   The local equivalent is `python -m streamlit run roadmap_app.py` from the root.
   The broader `app.py` is a different application.
3. In **Advanced settings**, explicitly select **Python 3.12**. Cloud installs
   the root `requirements.txt`; it does not need `requirements-dev.txt`.
4. Create a dedicated hosted-beta OpenAI project/key, separate from development.
   Privately enter the root-level TOML strings shown above in Cloud's **Secrets**
   settings. Use `ROADMAP_ENVIRONMENT = "beta"`, a daily limit from `"1"` through
   `"10"`, and initially `ROADMAP_GENERATION_ENABLED = "false"`. Never commit the
   real key. Root-level secrets become environment variables; no browser key
   input is required. See the official [deployment procedure](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).
5. Check startup/build logs and open the hosted form. Submit valid inputs while
   disabled: expect a safe disabled message, no generation-outcome log, and no
   API request. Enable generation by changing the string to `"true"`, restarting
   if needed, and perform the separately authorized manual quality checks for
   all three purposes. A successful attempt should display and download the
   same Markdown and emit one sanitized outcome record in the app logs.
6. Verify the kill switch after obtaining a result: change the setting back to
   `"false"`, apply/restart as needed, and submit again. No new API request should
   occur. Without a restart, existing session results/downloads remain usable;
   a server restart may clear sessions. Already-running API calls can finish.
7. Inspect the dedicated project's usage and configure appropriate usage alerts
   and available project rate limits. Alerts are not a hard spending cap. Check
   usage during the two-tester beta and disable generation if necessary. A
   restart clears the app's process-local quota; do not treat a reboot as a
   durable allowance check. Confirm the single-process assumption and retain
   the quota limitations documented above.
8. Have at least one external tester open the hosted URL, generate, read, and
   download a roadmap without repository access or their own key. Record the
   deployed revision and outcome before considering issue #32 complete.

Before deployment, verify a fresh installation on a machine with package-index
access: create a new Python 3.12 virtual environment, install
`requirements-dev.txt`, and run `python -m pytest -q`. For a credential-free UI
smoke check, unset `OPENAI_API_KEY`, launch the entrypoint, and confirm that the
form opens and a valid submission receives a safe unavailable message. No paid
call is needed. The hardening work's temporary clean-install attempt could not
resolve `openai==2.9.0` from its available package source; clean installation is
therefore **not yet verified**, despite passing tests in the existing environment.
