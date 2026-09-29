import json
import os
import re
import time
from typing import Protocol
from ..prompts.editor import EDITOR_SYSTEM

class LLMProvider(Protocol):
    name: str
    def process(self, title: str, source: str, content: str) -> dict: ...

class MockProvider:
    name = "mock"
    def process(self, title: str, source: str, content: str) -> dict:
        excerpt = re.sub(r"\s+", " ", content).strip()[:720]
        return {"title":title,"summary":excerpt,"what_happened":excerpt,"why_it_matters":"","background":"","upsc_relevance":"Editorial processing was unavailable; only the publisher's supplied headline and summary are shown.","gs_papers":[],"topics":[],"key_facts":[],"prelims_points":[],"mains_angles":[],"important_terms":[],"quiz_questions":[]}

class GeminiProvider:
    name = "gemini-2.5-flash"
    def __init__(self, api_key: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)
    def process(self, title: str, source: str, content: str) -> dict:
        prompt=f"{EDITOR_SYSTEM}\n\nUse only this supplied source. Source name: {source}\nTitle: {title}\n\nSOURCE TEXT:\n{content}\n\nReturn JSON only."
        response=self.client.models.generate_content(model=self.name,contents=prompt,config={"response_mime_type":"application/json"})
        data=json.loads(response.text or "{}")
        required=("title","summary","what_happened","why_it_matters","background","upsc_relevance","gs_papers","topics","key_facts","prelims_points","mains_angles","important_terms","quiz_questions")
        if any(key not in data for key in required):raise ValueError("Gemini response is missing required structured fields")
        return data

def get_provider() -> LLMProvider:
    if os.getenv("LLM_PROVIDER", "gemini").lower() == "mock" or not os.getenv("GEMINI_API_KEY"):
        return MockProvider()
    return GeminiProvider(os.environ["GEMINI_API_KEY"])

def process_with_retry(provider: LLMProvider, title: str, source: str, content: str, retries: int=2) -> dict:
    error=None
    for attempt in range(retries+1):
        try:return provider.process(title,source,content)
        except Exception as exc:
            error=exc
            if attempt<retries:time.sleep(0.25*(2**attempt))
    raise RuntimeError("Content processing failed after bounded retries") from error

# Backwards-compatible helper for local experiments. No API key means safe mock output.
def transform_source(text: str) -> dict:
    return process_with_retry(get_provider(), "Supplied article", "User supplied source", text)
