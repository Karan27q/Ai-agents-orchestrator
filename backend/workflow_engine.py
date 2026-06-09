import json
import asyncio
import httpx
import re
import datetime
import threading
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import os

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    genai = None
    HAS_GENAI = False

from database import get_db_context

import models
import llm_cache

# Global HTTP client pool for connection reuse (critical for throughput)
_http_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

async def get_http_client() -> httpx.AsyncClient:
    """Get or create a pooled HTTP client for connection reuse."""
    global _http_client
    
    if _http_client is None or _http_client.is_closed:
        # Create pooled client with connection limits optimized for throughput
        limits = httpx.Limits(
            max_connections=100,           # Max concurrent connections
            max_keepalive_connections=20,  # Reuse connections
            keepalive_expiry=30.0,        # Keep connections alive for 30s
        )
        _http_client = httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(30.0, connect=10.0),  # 30s total, 10s connect
            http2=True,  # Enable HTTP/2 for multiplexing
        )
    
    return _http_client

class WorkflowExecutionEngine:
    def __init__(self, db: Session, run_id: int):
        self.db = db
        self.run_id = run_id
        self.node_outputs: Dict[str, Any] = {}
        self.logs: List[str] = []
        self.log_flush_count = 0

    def log(self, message: str):
        """Log with batch flushing to reduce database writes."""
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.logs.append(log_line)
        print(log_line)
        
        # Batch log writes - only flush every 10 logs
        self.log_flush_count += 1
        if self.log_flush_count >= 10:
            self._flush_logs()
            self.log_flush_count = 0

    def _flush_logs(self):
        """Flush accumulated logs to database."""
        try:
            run = self.db.query(models.WorkflowRun).filter(
                models.WorkflowRun.id == self.run_id
            ).first()
            if run:
                run.logs = "\n".join(self.logs)
                self.db.commit()
        except Exception as e:
            print(f"Error flushing logs: {e}")

    def resolve_variables(self, text: str) -> str:
        """Replaces placeholders like {{node_id.field}} with values from self.node_outputs."""
        if not text:
            return ""
            
        def replacer(match):
            path = match.group(1).split(".")
            node_id = path[0]
            field = path[1] if len(path) > 1 else "output"
            
            val = self.node_outputs.get(node_id, {})
            if isinstance(val, dict):
                return str(val.get(field, match.group(0)))
            return str(val)

        return re.sub(r"\{\{([^}]+)\}\}", replacer, str(text))

    async def execute(self):
        self.log(f"Starting workflow execution run #{self.run_id}")
        run = self.db.query(models.WorkflowRun).filter(
            models.WorkflowRun.id == self.run_id
        ).first()
        if not run:
            self.log("Workflow run record not found. Aborting.")
            return

        run.status = "running"
        self.db.commit()

        try:
            workflow = run.workflow
            workflow_data = json.loads(workflow.workflow_json)
            
            nodes = workflow_data.get("nodes", [])
            edges = workflow_data.get("edges", [])
            
            # Map nodes by ID
            node_map = {n["id"]: n for n in nodes}
            
            # Build graph and adjacency list
            adj_list: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
            in_degree: Dict[str, int] = {n["id"]: 0 for n in nodes}
            
            for edge in edges:
                source = edge["source"]
                target = edge["target"]
                if source in adj_list and target in in_degree:
                    adj_list[source].append(target)
                    in_degree[target] += 1
            
            # Find entry nodes (in-degree 0)
            queue = [nid for nid, deg in in_degree.items() if deg == 0]
            
            visited_count = 0
            
            while queue:
                current_id = queue.pop(0)
                node = node_map[current_id]
                visited_count += 1
                
                self.log(f"Running node: '{node.get('data', {}).get('label', current_id)}' (type: {node.get('type')})")
                
                try:
                    output = await self.run_node(node)
                    self.node_outputs[current_id] = output
                    self.log(f"Node '{current_id}' completed. Output: {str(output)[:150]}...")
                except Exception as e:
                    self.log(f"ERROR executing node '{current_id}': {str(e)}")
                    run.status = "failed"
                    run.completed_at = datetime.datetime.utcnow()
                    self._flush_logs()
                    self.db.commit()
                    return
                
                # Check for branching/conditional outputs
                next_nodes = adj_list[current_id]
                if node.get("type") == "conditional":
                    branch = output.get("branch", "true")
                    self.log(f"Conditional path evaluated to: '{branch}' branch.")
                    filtered_next = []
                    for edge in edges:
                        if edge["source"] == current_id:
                            source_handle = edge.get("sourceHandle", "true")
                            if source_handle == branch:
                                filtered_next.append(edge["target"])
                    next_nodes = filtered_next

                for neighbor in next_nodes:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            
            self.log(f"Workflow execution completed. Executed {visited_count} nodes.")
            run.status = "completed"
            run.completed_at = datetime.datetime.utcnow()
            run.results = json.dumps(self.node_outputs)
            self._flush_logs()
            self.db.commit()

        except Exception as e:
            self.log(f"Critical execution failure: {str(e)}")
            run.status = "failed"
            run.completed_at = datetime.datetime.utcnow()
            self._flush_logs()
            self.db.commit()

    async def run_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        node_type = node.get("type")
        node_data = node.get("data", {})
        
        if node_type == "trigger":
            return {"status": "triggered", "timestamp": str(datetime.datetime.utcnow())}
            
        elif node_type == "http_request":
            url = self.resolve_variables(node_data.get("url", ""))
            method = node_data.get("method", "GET").upper()
            headers_raw = node_data.get("headers", "{}")
            body_raw = node_data.get("body", "")
            
            try:
                headers = json.loads(self.resolve_variables(headers_raw))
            except Exception:
                headers = {}
                
            body = self.resolve_variables(body_raw)
            
            self.log(f"HTTP {method} {url}")
            
            # Use pooled client instead of creating new one
            client = await get_http_client()
            try:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                elif method == "POST":
                    if headers.get("Content-Type") == "application/json":
                        try:
                            json_body = json.loads(body)
                            response = await client.post(url, headers=headers, json=json_body)
                        except Exception:
                            response = await client.post(url, headers=headers, content=body)
                    else:
                        response = await client.post(url, headers=headers, content=body)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                try:
                    resp_json = response.json()
                    return {
                        "status_code": response.status_code,
                        "data": resp_json
                    }
                except Exception:
                    return {
                        "status_code": response.status_code,
                        "text": response.text[:1000]  # Limit response size
                    }
            except httpx.TimeoutException:
                raise RuntimeError(f"HTTP request timeout to {url}")
            except Exception as e:
                raise RuntimeError(f"HTTP request failed: {str(e)}")
                    
        elif node_type == "llm_prompt":
            prompt_template = node_data.get("prompt", "")
            resolved_prompt = self.resolve_variables(prompt_template)
            
            self.log(f"Executing LLM prompt: {resolved_prompt[:100]}...")
            
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not HAS_GENAI or not gemini_key:
                await asyncio.sleep(1.5)
                return {"text": f"[Mock LLM Response]: {resolved_prompt}"}

            try:
                cached = llm_cache.get("gemini-1.5-flash", "", resolved_prompt)
                if cached is not None:
                    return {"text": cached}
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: model.generate_content(resolved_prompt)
                )
                llm_cache.set("gemini-1.5-flash", "", resolved_prompt, response.text)
                return {"text": response.text}
            except Exception as e:
                self.log(f"Gemini execution failed: {str(e)}")
                return {"text": f"[Gemini fallback response due to error: {str(e)}]"}
                
        elif node_type == "delay":
            seconds = int(node_data.get("seconds", 1))
            self.log(f"Sleeping for {seconds} seconds...")
            await asyncio.sleep(seconds)
            return {"status": f"slept {seconds}s"}
            
        elif node_type == "slack_message":
            webhook_url = self.resolve_variables(node_data.get("webhook_url", ""))
            message_text = self.resolve_variables(node_data.get("message", ""))
            
            if not webhook_url:
                self.log("Slack Webhook URL is empty. Skipping.")
                return {"status": "skipped", "reason": "empty webhook url"}
                
            self.log(f"Posting to Slack: {message_text[:100]}...")
            client = await get_http_client()
            try:
                resp = await client.post(webhook_url, json={"text": message_text})
                return {
                    "status_code": resp.status_code,
                    "text": resp.text[:500]
                }
            except Exception as e:
                raise RuntimeError(f"Slack post failed: {str(e)}")
                
        elif node_type == "conditional":
            ref_val = self.resolve_variables(node_data.get("reference_value", ""))
            comp_val = self.resolve_variables(node_data.get("comparison_value", ""))
            operator = node_data.get("operator", "equals")
            
            self.log(f"Evaluating conditional: '{ref_val}' {operator} '{comp_val}'")
            
            is_true = False
            if operator == "equals":
                is_true = str(ref_val).strip() == str(comp_val).strip()
            elif operator == "contains":
                is_true = str(comp_val).strip() in str(ref_val).strip()
                
            return {"branch": "true" if is_true else "false"}
            
        else:
            raise ValueError(f"Unknown node type: {node_type}")

def start_workflow_run(run_id: int):
    """Start workflow execution in the background using a dedicated DB session."""
    async def _background_execution():
        with get_db_context() as db:
            engine = WorkflowExecutionEngine(db, run_id)
            await engine.execute()

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_background_execution())
    except RuntimeError:
        background_loop = asyncio.new_event_loop()

        def run_loop(loop: asyncio.AbstractEventLoop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(
            target=run_loop,
            args=(background_loop,),
            daemon=True
        )
        thread.start()
        asyncio.run_coroutine_threadsafe(_background_execution(), background_loop)
