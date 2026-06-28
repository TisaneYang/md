# PilotAgent

PilotAgent is an upper-layer controller for MindDrive. It reads upstream JSON tasks,
calls a cloud multimodal model, overrides route meta-actions, and applies optional
post-inference speed middleware to MindDrive speed meta-actions.

The prompt is intentionally empty for now. Fill `pilot_agent/prompt.py` when the
business rules are finalized.

## Upstream JSON

```json
{
  "general_plan": "short high-level plan",
  "mermaid_graph": "graph TD; ...",
  "explain": "extra details not captured by Mermaid",
  "timestamp": 1.0,
  "information_source": "driver"
}
```

`information_source` records who issued the upstream instruction, for example
`driver` or `administrator`.

The agent also passes `vehicle_position` into the cloud decision request. Its
intersection flag comes from CARLA `waypoint.is_junction` and is used to separate
junction-only actions (`<turn_left>`, `<turn_right>`, `<straight>`) from regular
lane-follow/lane-change actions.

## Runtime

Set `PILOT_AGENT_CONFIG` before running MindDrive:

```bash
export PILOT_AGENT_CONFIG=/Users/bytedance/MyProj/md/PilotAgent/configs/pilot_agent.json
```

Run the optional upstream HTTP server:

```bash
python3 -m PilotAgent.pilot_agent.http_server --host 127.0.0.1 --port 8765
```

Then send upstream tasks to:

```text
POST /upstream
GET  /latest
```

## Cloud Providers

`pilot_agent/cloud_vlm_client.py` supports OpenAI-compatible chat-completions APIs,
DashScope compatible mode, and Volcengine Ark compatible mode behind one interface.

## Speed Middleware

The speed middleware runs after MindDrive outputs a speed meta-action. It does not
modify MindDrive logits or ask the cloud model to select candidate speed actions.
