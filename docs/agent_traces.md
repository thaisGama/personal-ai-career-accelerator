# Agent Traces

An agent trace is a JSON log of each step the weekly planner agent takes, including tool inputs and outputs.

## Location
- Saved under `data/traces/` as `trace_YYYY-MM-DD_HH-MM-SS.json`

## Fields
Each trace entry includes:
- `step_name`: the logical step in the agent flow
- `tool_name`: the tool invoked (or `internal`)
- `tool_input`: inputs passed to the tool
- `tool_output_summary`: short, human-readable summary
- `tool_output_full`: full output payload
- `ts`: ISO timestamp of the step

## Example
```json
[
  {
    "step_name": "retrieve_memory",
    "tool_name": "tool_retrieve_memory",
    "tool_input": {
      "goal": "learn embeddings",
      "preferences": {
        "text": "prefer practical steps"
      },
      "k": 8
    },
    "tool_output_summary": "memory_used=True hits=3",
    "tool_output_full": {
      "memory_context": "Top relevant notes...",
      "memory_hits": [
        {
          "id": "mem_3",
          "text": "Finished embedding basics",
          "score": 0.812
        }
      ],
      "audit": {
        "memory_used": true,
        "memory_snippets_count": 3
      }
    },
    "ts": "2025-01-12T09:41:02"
  }
]
```

## ReAct Loop Traces
In ReAct mode, each trace includes controller steps where the LLM chooses the next tool.

Action schema:
```json
{"action":"tool","tool_name":"retrieve_memory","args":{"k":8}}
```
```json
{"action":"final","result":{"weekly_plan_path":"...","linkedin_path":"...","next_task":"..."}}
```

Mock fixtures must be JSON Lines (`.jsonl`), one JSON object per line.
Example JSONL file:
```json
{"action":"tool","tool_name":"retrieve_memory","args":{"k":8}}
{"action":"tool","tool_name":"generate_weekly_plan","args":{}}
```

Tiny example (two steps):
```json
[
  {
    "step_name": "controller",
    "tool_name": "controller",
    "tool_output_summary": "action=tool",
    "tool_output_full": {
      "action": {
        "action": "tool",
        "tool_name": "retrieve_memory",
        "args": {"k": 8}
      }
    }
  },
  {
    "step_name": "retrieve_memory",
    "tool_name": "tool_retrieve_memory",
    "tool_output_summary": "memory_used=False hits=0"
  }
]
```
