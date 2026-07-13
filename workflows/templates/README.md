# A-Cal Workflow Templates

Pre-built workflow configs you can import and customize. Each file is a JSON
workflow definition compatible with the A-Cal Workflow Builder.

## Installing

1. Open A-Cal in Developer mode
2. Open the Workflow Builder panel
3. Click "Import" and select a template file, or copy the JSON into the editor

## Available Templates

| Template | What it does |
|----------|-------------|
| `daily_briefing.json` | Fetch today's events, summarize with LLM, email the summary |
| `conflict_resolver.json` | Detect scheduling conflicts and trigger swarm negotiation |
| `focus_time_protector.json` | Protect marked focus blocks from being overwritten |
| `weekly_review.json` | Summarize the past week and plan the next using self-model insights |

## Customizing

Edit any template in the Workflow Builder or as JSON. Change prompts, add
nodes, reorder edges, or chain multiple workflows together. Share your
customized version on the marketplace.
