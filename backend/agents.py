import os
import json
import asyncio
from typing import AsyncGenerator, Callable, List, Dict, Any

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    genai = None
    HAS_GENAI = False

# Setup Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if HAS_GENAI and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class ResearchAgentOrchestrator:
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model_name = model_name
        self.api_available = bool(GEMINI_API_KEY and HAS_GENAI)

    async def _call_llm(self, prompt: str, system_instruction: str = "") -> str:
        """Helper to invoke Gemini API with a system prompt, or return local mock if key not set."""
        if not self.api_available:
            await asyncio.sleep(1.0) # Simulate network lag
            # Return simple fallback text based on prompt
            if "PLANNER" in system_instruction:
                return json.dumps({
                    "outline": [
                        "1. Overview and Core Drivers",
                        "2. Market Growth & Opportunities",
                        "3. Challenges and Future Trends"
                    ]
                })
            elif "CRITIC" in system_instruction:
                return "The research is solid but needs more specific statistics on early-stage funding and regulatory challenges."
            elif "WRITER" in system_instruction:
                return "## Final Research Report\n\n### 1. Overview\nAI startups in India are growing rapidly. India ranks highly in AI talent concentration...\n\n### 2. Market Growth\nGrowth is driven by deeptech investments, local cloud infrastructure, and massive engineering pools...\n\n### 3. Challenges\nKey challenges include access to specialized GPU compute, high cost of foundation model training, and regulatory ambiguity around data sovereignty."
            elif "CITATION" in system_instruction:
                return "## Final Research Report\n\n### 1. Overview\nAI startups in India are growing rapidly [1]. India ranks highly in AI talent concentration [2]...\n\n### References\n[1] NASSCOM Deeptech Report 2025\n[2] Stanford AI Index Report 2025"
            return f"Mock response for prompt: {prompt[:50]}..."

        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )
            # Use run_in_executor since genai is synchronous (or use async client if supported)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: model.generate_content(prompt)
            )
            return response.text
        except Exception as e:
            print(f"Error calling Gemini: {e}")
            return f"Error executing model: {str(e)}"

    async def run_research_flow(
        self, 
        topic: str, 
        status_callback: Callable[[str, str], Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes the Multi-Agent Research flow:
        Planner -> Research -> Critic -> Writer -> Citation
        Streams progress and logs, then streams final report tokens.
        """
        
        async def send_status(agent: str, msg: str, data: Any = None):
            if status_callback:
                if asyncio.iscoroutinefunction(status_callback):
                    await status_callback(agent, msg)
                else:
                    status_callback(agent, msg)
            yield {"type": "status", "agent": agent, "message": msg, "data": data}

        # -------------------------------------------------------------
        # 1. PLANNER AGENT
        # -------------------------------------------------------------
        async for item in send_status("Planner Agent", f"Creating research outline for: '{topic}'"): yield item
        
        planner_instruction = (
            "You are a Planner Agent. Create a structured outline (in JSON format) for research on the user's topic. "
            "Respond ONLY with a JSON object containing an 'outline' list of sections to research. "
            "Example: { \"outline\": [\"Section 1\", \"Section 2\"] }"
        )
        planner_resp = await self._call_llm(f"Topic: {topic}", system_instruction=planner_instruction)
        
        try:
            # Clean response text in case LLM wraps it in ```json
            cleaned_resp = planner_resp.strip()
            if cleaned_resp.startswith("```json"):
                cleaned_resp = cleaned_resp[7:]
            if cleaned_resp.endswith("```"):
                cleaned_resp = cleaned_resp[:-3]
            outline_data = json.loads(cleaned_resp.strip())
            outline = outline_data.get("outline", [topic])
        except Exception:
            outline = [f"General overview of {topic}", f"Key details of {topic}", f"Future perspectives of {topic}"]
            
        async for item in send_status("Planner Agent", "Research outline finalized.", {"outline": outline}): yield item

        # -------------------------------------------------------------
        # 2. RESEARCH AGENT
        # -------------------------------------------------------------
        research_notes = []
        for i, section in enumerate(outline, 1):
            async for item in send_status("Research Agent", f"Gathering facts for Section {i}: '{section}'"): yield item
            
            research_instruction = (
                "You are an expert Research Agent. Research the provided subtopic. "
                "Output clear, factual notes, statistics, and references if possible. Be concise."
            )
            notes = await self._call_llm(f"Research Topic: {topic}\nSection: {section}", system_instruction=research_instruction)
            research_notes.append(f"### Research notes for {section}:\n{notes}")
            
            # Yield progress increment
            await asyncio.sleep(0.5)

        combined_notes = "\n\n".join(research_notes)
        async for item in send_status("Research Agent", "Fact gathering completed."): yield item

        # -------------------------------------------------------------
        # 3. CRITIC AGENT
        # -------------------------------------------------------------
        async for item in send_status("Critic Agent", "Reviewing gathered research notes for completeness and bias"): yield item
        
        critic_instruction = (
            "You are a Critic Agent. Evaluate the gathered research notes. "
            "Identify missing aspects, gaps in logic, or details that require additional verification."
        )
        criticism = await self._call_llm(
            f"Topic: {topic}\n\nGathered Notes:\n{combined_notes}", 
            system_instruction=critic_instruction
        )
        async for item in send_status("Critic Agent", f"Critique complete: {criticism[:150]}..."): yield item

        # -------------------------------------------------------------
        # 4. WRITER AGENT
        # -------------------------------------------------------------
        async for item in send_status("Writer Agent", "Synthesizing notes and critique into a comprehensive draft"): yield item
        
        writer_instruction = (
            "You are a Writer Agent. Write a professional, comprehensive, and well-structured markdown report "
            "using the gathered notes and address the feedback from the Critic."
        )
        draft = await self._call_llm(
            f"Topic: {topic}\n\nNotes:\n{combined_notes}\n\nCritic Feedback:\n{criticism}", 
            system_instruction=writer_instruction
        )
        async for item in send_status("Writer Agent", "Draft report generated."): yield item

        # -------------------------------------------------------------
        # 5. CITATION AGENT
        # -------------------------------------------------------------
        async for item in send_status("Citation Agent", "Adding formal citations, links, and formatting bibliography"): yield item
        
        citation_instruction = (
            "You are a Citation Agent. Add footnotes/citations (e.g. [1], [2]) and a 'References' section "
            "at the end of the markdown report. Ensure formatting is clean, professional, and elegant."
        )
        final_report = await self._call_llm(
            f"Draft Report:\n{draft}", 
            system_instruction=citation_instruction
        )
        
        async for item in send_status("Citation Agent", "Report finalized with full citations."): yield item

        # -------------------------------------------------------------
        # Stream the actual report content token by token (or chunk by chunk)
        # -------------------------------------------------------------
        # Since we have the final report, let's stream it back in smaller chunks
        # to simulate token-by-token generation for that rich AI feel.
        chunk_size = 64
        for idx in range(0, len(final_report), chunk_size):
            yield {
                "type": "token",
                "content": final_report[idx:idx + chunk_size]
            }
            await asyncio.sleep(0.05) # fast streaming
            
        yield {"type": "completed", "report": final_report}
