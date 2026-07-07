"""LLM client for the vLLM-served Qwen model (OpenAI-compatible + instructor),
plus a deterministic mock for offline runs (--mock-llm / LLM_MOCK=true).

instructor Mode.JSON works on any vLLM deployment (tools mode needs server-side
flags). use_guided_json additionally passes the response schema to vLLM's guided
decoding for guaranteed-valid JSON; disable it in llm_config.yaml if the server
rejects extra_body."""

import re

import requests

from src.common.config import Settings
from src.validation.wiki_schema import (
    EntitySource,
    EntityWikiProfile,
    PageRecordsResponse,
    PageWikiRecordLLM,
)


class LLMError(RuntimeError):
    pass


def ping_llm(settings: Settings) -> None:
    url = settings.llm_base_url.rstrip("/") + "/models"
    hint = (
        f"vLLM unreachable at {settings.llm_base_url} — start the server "
        "(or rerun with --mock-llm for an offline test)."
    )
    try:
        resp = requests.get(
            url, timeout=10, headers={"Authorization": f"Bearer {settings.llm_api_key}"}
        )
    except requests.RequestException as exc:
        raise LLMError(f"{hint} ({exc})") from exc
    if resp.status_code >= 400:
        raise LLMError(f"LLM endpoint {url} returned HTTP {resp.status_code}. {hint}")


class QwenClient:
    def __init__(self, settings: Settings):
        import instructor
        from openai import OpenAI

        self.settings = settings
        base = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=float(settings.llm.get("request_timeout_sec", 300)),
        )
        self.client = instructor.from_openai(base, mode=instructor.Mode.JSON)
        self.model_name = settings.qwen_model

    def generate(self, response_model, prompt: str):
        llm = self.settings.llm
        kwargs = {}
        extra_body = {}
        if llm.get("use_guided_json", True):
            extra_body["guided_json"] = response_model.model_json_schema()
        if not llm.get("enable_thinking", True):
            extra_body["think"] = False
        if extra_body:
            kwargs["extra_body"] = extra_body
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=float(llm.get("temperature", 0.1)),
            max_tokens=int(llm.get("max_tokens", 4096)),
            max_retries=int(llm.get("max_retries", 2)),
            response_model=response_model,
            **kwargs,
        )


class MockQwenClient:
    """Offline stand-in. Reads markers from the prompt/page content:
    MOCK_EMPTY (irrelevant page -> no records), MOCK_BAD_ENUM (record with an
    invalid category, to exercise validation), MOCK_RAISE (generation failure),
    MOCK_ENTITY: <name> (entity for the canned record)."""

    model_name = "mock-qwen"

    def generate(self, response_model, prompt: str):
        if "MOCK_RAISE" in prompt:
            raise LLMError("mock generation failure (MOCK_RAISE marker)")
        if response_model is PageRecordsResponse:
            return self._page_records(prompt)
        if response_model is EntityWikiProfile:
            return self._entity_profile(prompt)
        raise LLMError(f"MockQwenClient has no canned output for {response_model!r}")

    @staticmethod
    def _prompt_field(prompt: str, label: str) -> str:
        match = re.search(rf"^{label}:\s*\n(.+)$", prompt, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _page_records(self, prompt: str) -> PageRecordsResponse:
        if "MOCK_EMPTY" in prompt:
            return PageRecordsResponse(records=[])

        source_url = self._prompt_field(prompt, "Source URL")
        source_title = self._prompt_field(prompt, "Source title")
        source_domain = self._prompt_field(prompt, "Source domain")

        entity_match = re.search(r"^MOCK_ENTITY:\s*(.+)$", prompt, re.MULTILINE)
        entity = entity_match.group(1).strip() if entity_match else "Mock Battery Company"

        # evidence must be a real line from the page so the grounding check passes;
        # slice off the trailing schema block so it can never be picked as evidence
        page_content = prompt.split("Crawl4AI Markdown content:")[-1].split("Return a JSON object")[0]
        evidence = fallback = ""
        for line in page_content.splitlines():
            line = line.strip()
            if len(line) >= 40 and not line.startswith(("#", "MOCK_")):
                fallback = fallback or line
                if entity.casefold() in line.casefold():
                    evidence = line
                    break
        evidence = evidence or fallback

        bad = "MOCK_BAD_ENUM" in prompt
        record = PageWikiRecordLLM(
            entity_type="spaceship" if bad else "company",
            entity_name=entity,
            canonical_name=entity,
            title=entity,
            overview=f"{entity} is involved in Georgia EV supply-chain activity per the source page.",
            location="Georgia",
            state="Georgia",
            country="United States",
            ev_relevance=f"{entity} is connected to EV supply-chain activity in Georgia.",
            supply_chain_category="warp_drives" if bad else "battery_materials",
            details="battery materials",
            source_url=source_url,
            source_title=source_title,
            source_domain=source_domain,
            evidence_text=evidence,
            confidence_score=0.9,
        )
        return PageRecordsResponse(records=[record])

    def _entity_profile(self, prompt: str) -> EntityWikiProfile:
        canonical_match = re.search(r'"canonical_name":\s*"([^"]+)"', prompt)
        canonical = canonical_match.group(1) if canonical_match else "Mock Entity"
        entity_type_match = re.search(r'"entity_type":\s*"([^"]+)"', prompt)
        pairs = re.findall(
            r'"source_url":\s*"([^"]*)"[\s\S]*?"evidence_text":\s*"([^"]*)"', prompt
        )
        seen = set()
        sources = []
        for url, evidence in pairs:
            if url and url not in seen:
                seen.add(url)
                sources.append(EntitySource(source_url=url, evidence_text=evidence))
        return EntityWikiProfile(
            canonical_name=canonical,
            entity_type=entity_type_match.group(1) if entity_type_match else "company",
            title=canonical,
            overview=f"{canonical} profile merged from {len(sources)} source record(s).",
            locations=["Georgia"],
            supply_chain_categories=["battery_materials"],
            sources=sources,
            confidence_score=0.9,
        )


def get_llm_client(settings: Settings, mock: bool = False):
    if mock or settings.llm_mock:
        return MockQwenClient()
    ping_llm(settings)
    return QwenClient(settings)
