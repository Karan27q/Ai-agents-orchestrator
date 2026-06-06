# Automated Pipelines Guide & Examples

This document explains how the **Workflow Automation Engine** in the AI Orchestrator works, describes the supported node types, explains how to pass variables between nodes, and provides structural JSON examples you can import or use as references.

---

## 1. Core Concepts

A pipeline is represented as a **Directed Acyclic Graph (DAG)** composed of:
1. **Nodes**: Discrete execution steps (e.g., triggering the workflow, making HTTP requests, prompting the Gemini LLM, branching dynamically).
2. **Edges**: Connections defining execution order. Edges link a `source` node to a `target` node.
3. **Variables**: Placeholders in text/headers/URLs that reference outputs from previous nodes using the `{{node_id.field}}` syntax.

---

## 2. Supported Node Types & Output Schemas

| Node Type (`type`) | Purpose | Key Inputs (`data`) | Output Structure (`node_outputs`) |
| :--- | :--- | :--- | :--- |
| **`trigger`** | Entry point of the workflow. | None. | `{"status": "triggered", "timestamp": "2026-05-27..."}` |
| **`llm_prompt`** | Prompts the Gemini LLM. | `prompt`: (String, supports templates) | `{"text": "LLM response content"}` |
| **`http_request`** | Sends an external API call. | `url`, `method` (`GET`/`POST`), `headers` (JSON string), `body` | `{"status_code": 200, "data": { ... }}` (if JSON response)<br>or `{"status_code": 200, "text": "..."}` |
| **`conditional`** | Dynamic branch execution. | `reference_value`, `comparison_value`, `operator` (`equals`, `contains`) | `{"branch": "true"}` or `{"branch": "false"}` |
| **`delay`** | Pauses execution. | `seconds`: (Integer, e.g., `5`) | `{"status": "slept 5s"}` |
| **`slack_message`**| Sends a message to Slack. | `webhook_url`, `message` (supports templates) | `{"status_code": 200, "text": "ok"}` |

---

## 3. How Variable Resolution Works

You can read values from prior nodes using double curly braces: `{{node_id.field}}`. 
* If `field` is omitted (e.g., `{{node_id}}`), it defaults to `output`.
* If the output of a node is a dictionary, you can extract nested properties (e.g., `{{node_id.status_code}}` or `{{node_id.data}}`).

### Variable Binding Example:
Imagine you have an HTTP request node with `id: "fetch_weather"`.
It returns:
```json
{
  "status_code": 200,
  "data": {
    "temp": 28,
    "condition": "Rainy"
  }
}
```
You can reference this temperature and condition in a subsequent **LLM Prompt** node:
```text
The current weather condition is {{fetch_weather.data.condition}} and the temperature is {{fetch_weather.data.temp}} degrees. 
Draft a polite email advising the team to carry an umbrella.
```

---

## 4. Pipeline JSON Examples

You can construct workflows in the visual UI or save them to the database in the `workflow_json` column. Below are two production-ready examples.

### Example A: AI News Summarizer & Slack Poster
This pipeline:
1. Triggers.
2. Fetches the latest tech news via an HTTP GET request.
3. Feeds the news text into the Gemini LLM for a structured summary.
4. Posts the summary to a Slack channel via a Slack Webhook.

```json
{
  "nodes": [
    {
      "id": "start_trigger",
      "type": "trigger",
      "data": {
        "label": "Start Pipeline"
      }
    },
    {
      "id": "fetch_news",
      "type": "http_request",
      "data": {
        "label": "Fetch News API",
        "url": "https://api.spaceflightnewsapi.net/v4/articles/?limit=3",
        "method": "GET",
        "headers": "{\"Content-Type\": \"application/json\"}"
      }
    },
    {
      "id": "summarize_llm",
      "type": "llm_prompt",
      "data": {
        "label": "Summarize News",
        "prompt": "Here is the raw news data: {{fetch_news.text}}. Summarize the key points in 3 bullet points, using a professional tone."
      }
    },
    {
      "id": "slack_notification",
      "type": "slack_message",
      "data": {
        "label": "Post to Tech Slack",
        "webhook_url": "REDACTED_SLACK_WEBHOOK_URL",
        "message": "📢 *Daily Tech News Summary*:\n{{summarize_llm.text}}"
      }
    }
  ],
  "edges": [
    {
      "id": "edge-1",
      "source": "start_trigger",
      "target": "fetch_news"
    },
    {
      "id": "edge-2",
      "source": "fetch_news",
      "target": "summarize_llm"
    },
    {
      "id": "edge-3",
      "source": "summarize_llm",
      "target": "slack_notification"
    }
  ]
}
```

---

### Example B: Conditional Customer Support Escalator (Branching DAG)
This pipeline:
1. Triggers.
2. Fetches a customer ticket status from a support API.
3. Evaluates if the status is **"Critical"**:
   * **If True**: Prompt the LLM to draft a high-priority response and post an escalation warning to Slack.
   * **If False**: Log the event and wait.

```json
{
  "nodes": [
    {
      "id": "trigger_start",
      "type": "trigger",
      "data": {
        "label": "Webhook Trigger"
      }
    },
    {
      "id": "get_ticket",
      "type": "http_request",
      "data": {
        "label": "Get Ticket Details",
        "url": "https://api.mycompany.com/tickets/latest",
        "method": "GET"
      }
    },
    {
      "id": "check_priority",
      "type": "conditional",
      "data": {
        "label": "Is High Priority?",
        "reference_value": "{{get_ticket.data.priority}}",
        "operator": "equals",
        "comparison_value": "high"
      }
    },
    {
      "id": "high_priority_draft",
      "type": "llm_prompt",
      "data": {
        "label": "Draft Urgent Reply",
        "prompt": "Draft an urgent support email for customer {{get_ticket.data.customer_name}} regarding: {{get_ticket.data.issue}}"
      }
    },
    {
      "id": "slack_alert",
      "type": "slack_message",
      "data": {
        "label": "Escalate on Slack",
        "webhook_url": "REDACTED_SLACK_WEBHOOK_URL",
        "message": "🔥 *Urgent Escalation* for ticket #{{get_ticket.data.id}}:\n{{high_priority_draft.text}}"
      }
    },
    {
      "id": "low_priority_delay",
      "type": "delay",
      "data": {
        "label": "Standard Queue Delay",
        "seconds": 5
      }
    }
  ],
  "edges": [
    {
      "id": "e-1",
      "source": "trigger_start",
      "target": "get_ticket"
    },
    {
      "id": "e-2",
      "source": "get_ticket",
      "target": "check_priority"
    },
    {
      "id": "e-3-true",
      "source": "check_priority",
      "sourceHandle": "true",
      "target": "high_priority_draft"
    },
    {
      "id": "e-4-true",
      "source": "high_priority_draft",
      "target": "slack_alert"
    },
    {
      "id": "e-3-false",
      "source": "check_priority",
      "sourceHandle": "false",
      "target": "low_priority_delay"
    }
  ]
}
```

---

## 5. Running the Pipeline
1. Open the **Workflows** tab in the browser user interface.
2. Build your graph by adding nodes (Trigger, HTTP Request, LLM, Conditional, Delay, Slack) and connecting them.
3. Configure each node's input settings using the details above.
4. Click **Run Workflow**. You will see the execution stream live logs node-by-node, storing results in the SQLite database automatically.
