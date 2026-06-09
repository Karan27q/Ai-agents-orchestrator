import os
import json
import asyncio
import threading
from typing import AsyncGenerator, Callable, List, Dict, Any, Optional

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    genai = None
    HAS_GENAI = False

import llm_cache

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "3"))
_llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

if HAS_GENAI and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class ResearchAgentOrchestrator:
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model_name = model_name
        self.api_available = bool(GEMINI_API_KEY and HAS_GENAI)

    async def _call_llm(self, prompt: str, system_instruction: str = "") -> str:
        cached = llm_cache.get(self.model_name, system_instruction, prompt)
        if cached is not None:
            return cached

        if not self.api_available:
            await asyncio.sleep(0.3)
            if "Planner" in system_instruction:
                result = json.dumps({
                    "outline": [
                        "1. Overview and Core Drivers",
                        "2. Market Growth & Opportunities",
                        "3. Challenges and Future Trends",
                    ]
                })
            elif "Critic" in system_instruction:
                result = "The research is solid but needs more specific statistics on early-stage funding and regulatory challenges."
            elif "Writer" in system_instruction:
                result = "## Final Research Report\n\n### 1. Overview\nAI startups in India are growing rapidly [1]...\n\n### References\n[1] NASSCOM Deeptech Report 2025"
            else:
                result = f"Mock response for prompt: {prompt[:50]}..."
            llm_cache.set(self.model_name, system_instruction, prompt, result)
            return result

        async with _llm_semaphore:
            try:
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_instruction,
                )
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, lambda: model.generate_content(prompt)
                )
                result = response.text
                llm_cache.set(self.model_name, system_instruction, prompt, result)
                return result
            except Exception as e:
                print(f"Error calling Gemini: {e}")
                return f"Error executing model: {str(e)}"

    async def _stream_llm(
        self, prompt: str, system_instruction: str = ""
    ) -> AsyncGenerator[str, None]:
        cached = llm_cache.get(self.model_name, system_instruction, prompt)
        if cached is not None:
            for i in range(0, len(cached), 64):
                yield cached[i : i + 64]
            return

        if not self.api_available:
            mock = "## Final Research Report\n\n(Mock streamed report content.)"
            llm_cache.set(self.model_name, system_instruction, prompt, mock)
            for i in range(0, len(mock), 64):
                yield mock[i : i + 64]
                await asyncio.sleep(0.02)
            return

        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        async def release_sem():
            _llm_semaphore.release()

        await _llm_semaphore.acquire()

        def producer():
            parts: List[str] = []
            try:
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_instruction,
                )
                for chunk in model.generate_content(prompt, stream=True):
                    if chunk.text:
                        parts.append(chunk.text)
                        asyncio.run_coroutine_threadsafe(queue.put(chunk.text), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(queue.put(f"Error: {e}"), loop)
            finally:
                full = "".join(parts)
                if full:
                    llm_cache.set(self.model_name, system_instruction, prompt, full)
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)
                asyncio.run_coroutine_threadsafe(release_sem(), loop)

        threading.Thread(target=producer, daemon=True).start()

        while True:
            piece = await queue.get()
            if piece is None:
                break
            yield piece

    async def run_research_flow(
        self,
        topic: str,
        status_callback: Callable[[str, str], Any] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async def send_status(agent: str, msg: str, data: Any = None):
            if status_callback:
                if asyncio.iscoroutinefunction(status_callback):
                    await status_callback(agent, msg)
                else:
                    status_callback(agent, msg)
            yield {"type": "status", "agent": agent, "message": msg, "data": data}

        # 1. PLANNER
        async for item in send_status("Planner Agent", f"Creating research outline for: '{topic}'"):
            yield item

        planner_instruction = (
            "You are a Planner Agent. Create a structured outline (in JSON format) for research on the user's topic. "
            "Respond ONLY with a JSON object containing an 'outline' list of sections to research. "
            'Example: { "outline": ["Section 1", "Section 2"] }'
        )
        planner_resp = await self._call_llm(f"Topic: {topic}", system_instruction=planner_instruction)

        try:
            cleaned_resp = planner_resp.strip()
            if cleaned_resp.startswith("```json"):
                cleaned_resp = cleaned_resp[7:]
            if cleaned_resp.endswith("```"):
                cleaned_resp = cleaned_resp[:-3]
            outline_data = json.loads(cleaned_resp.strip())
            outline = outline_data.get("outline", [topic])
        except Exception:
            outline = [
                f"General overview of {topic}",
                f"Key details of {topic}",
                f"Future perspectives of {topic}",
            ]

        async for item in send_status("Planner Agent", "Research outline finalized.", {"outline": outline}):
            yield item

        # 2. RESEARCH (parallel sections)
        research_instruction = (
            "You are an expert Research Agent. Research the provided subtopic. "
            "Output clear, factual notes, statistics, and references if possible. Be concise."
        )

        async for item in send_status(
            "Research Agent", f"Gathering facts for {len(outline)} sections in parallel..."
        ):
            yield item

        async def research_section(index: int, section: str):
            notes = await self._call_llm(
                f"Research Topic: {topic}\nSection: {section}",
                system_instruction=research_instruction,
            )
            return index, section, notes

        tasks = [asyncio.create_task(research_section(i, s)) for i, s in enumerate(outline)]
        research_results: List[Optional[tuple]] = [None] * len(outline)

        for finished in asyncio.as_completed(tasks):
            idx, section, notes = await finished
            research_results[idx] = (section, notes)
            async for item in send_status(
                "Research Agent", f"Completed Section {idx + 1}: '{section}'"
            ):
                yield item

        research_notes = [
            f"### Research notes for {section}:\n{notes}"
            for section, notes in research_results
        ]
        combined_notes = "\n\n".join(research_notes)

        async for item in send_status("Research Agent", "Fact gathering completed."):
            yield item

        # 3. CRITIC
        async for item in send_status(
            "Critic Agent", "Reviewing gathered research notes for completeness and bias"
        ):
            yield item

        critic_instruction = (
            "You are a Critic Agent. Evaluate the gathered research notes. "
            "Identify missing aspects, gaps in logic, or details that require additional verification."
        )
        criticism = await self._call_llm(
            f"Topic: {topic}\n\nGathered Notes:\n{combined_notes}",
            system_instruction=critic_instruction,
        )
        async for item in send_status("Critic Agent", f"Critique complete: {criticism[:150]}..."):
            yield item

        # 4. WRITER + CITATION (merged)
        async for item in send_status(
            "Writer Agent", "Writing final report with citations..."
        ):
            yield item

        writer_instruction = (
            "You are a Writer Agent. Write a professional, comprehensive, well-structured markdown report "
            "using the gathered notes and address the Critic's feedback. "
            "Include inline citations (e.g. [1], [2]) and a References section at the end."
        )
        writer_prompt = (
            f"Topic: {topic}\n\nNotes:\n{combined_notes}\n\nCritic Feedback:\n{criticism}"
        )

        final_parts: List[str] = []
        async for token in self._stream_llm(writer_prompt, system_instruction=writer_instruction):
            final_parts.append(token)
            yield {"type": "token", "content": token}

        final_report = "".join(final_parts)
        async for item in send_status("Writer Agent", "Report finalized with full citations."):
            yield item

        yield {"type": "completed", "report": final_report}
