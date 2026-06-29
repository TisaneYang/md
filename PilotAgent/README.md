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

## Roadside Reporting

PilotAgent can optionally report its latest `upstream` and `task_status` to RoadsideAgent after each cloud decision tick.

Configure `roadside_report` in `configs/pilot_agent.json`:

```json
{
  "roadside_report": {
    "enabled": false,
    "url": "http://127.0.0.1:8890/vehicles/state",
    "endpoint": "127.0.0.1:9101",
    "timeout_ms": 200
  }
}
```

Behavior:

- After a normal PilotAgent inference, it reports `vehicle_id`, `timestamp`, `endpoint`, `upstream`, and `task_status`.
- If the decision tick is reached but inference is skipped because `current_upstream is None`, it sends a heartbeat report with `vehicle_id`, `timestamp`, and `endpoint`.
- The ego vehicle id is taken from the CARLA hero actor in MindDrive's `run_step()`.

## Cloud Providers

`pilot_agent/cloud_vlm_client.py` supports OpenAI-compatible chat-completions APIs,
DashScope compatible mode, and Volcengine Ark compatible mode behind one interface.

## Speed Middleware

The speed middleware runs after MindDrive outputs a speed meta-action. It does not
modify MindDrive logits or ask the cloud model to select candidate speed actions.
