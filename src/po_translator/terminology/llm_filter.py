"""LLM-assisted terminology filtering and batch translation."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from po_translator.exceptions import POTranslatorError
from po_translator.llm.models import LLMClient, LLMRequest, Message
from po_translator.terminology.models import GlossaryTerm, TermCandidate, TermOrigin
from po_translator.translation.prompts import load_prompt_template

logger = logging.getLogger(__name__)


class LLMTermProcessor:
    """Interacts with LLM for structured candidate filtering and terminology translation."""

    @staticmethod
    def _clean_json_response(content: str) -> str:
        s = content.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        return s

    @classmethod
    async def filter_candidates(
        cls,
        candidates: Sequence[TermCandidate],
        client: LLMClient,
        max_batch_size: int = 50,
    ) -> list[GlossaryTerm]:
        """Filter candidate terms using LLM structured output. Returns confirmed terms."""
        if not candidates:
            return []

        template = load_prompt_template("glossary_filter.txt")
        approved_terms: list[GlossaryTerm] = []

        # Process in batches
        for i in range(0, len(candidates), max_batch_size):
            batch = candidates[i : i + max_batch_size]
            candidates_payload = [
                {"source": c.text, "frequency": c.frequency, "examples": c.examples[:2]}
                for c in batch
            ]

            prompt = template.replace("{candidates_json}", json.dumps(candidates_payload, ensure_ascii=False, indent=2))
            req = LLMRequest(
                system_prompt=prompt,
                messages=[Message(role="user", content="Analyze the candidates and return JSON.")],
                temperature=0.1,
                response_schema={"type": "object"},
            )

            # Retry once on malformed JSON
            data = None
            last_err = None
            for attempt in range(2):
                try:
                    resp = await client.complete(req)
                    cleaned = cls._clean_json_response(resp.content)
                    data = json.loads(cleaned)
                    break
                except (POTranslatorError, json.JSONDecodeError, OSError) as e:
                    last_err = e
                    logger.warning("Glossary filter parse failed on attempt %d: %s", attempt + 1, e)

            if data is None or not isinstance(data, dict) or "terms" not in data:
                logger.error("Failed to parse glossary filter response: %s", last_err)
                continue

            # Candidate lookup map for frequency
            cand_map = {c.text: c for c in batch}

            for item in data["terms"]:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source", "")).strip()
                keep = bool(item.get("keep", False))
                category = str(item.get("category", "general"))
                reason = str(item.get("reason", ""))

                if keep and source in cand_map:
                    cand = cand_map[source]
                    approved_terms.append(
                        GlossaryTerm(
                            id=GlossaryTerm.generate_id(source),
                            source=source,
                            target=None,
                            category=category,
                            description=reason,
                            frequency=cand.frequency,
                            locked=False,
                            created_by=TermOrigin.LLM,
                        )
                    )

        return approved_terms

    @classmethod
    async def translate_terms(
        cls,
        terms: Sequence[GlossaryTerm],
        source_lang: str,
        target_lang: str,
        client: LLMClient,
        max_batch_size: int = 50,
    ) -> list[GlossaryTerm]:
        """Translate approved glossary terms in batches using structured output."""
        if not terms:
            return []

        template = load_prompt_template("glossary_translate.txt")
        prompt_base = template.replace("{source_lang}", source_lang).replace("{target_lang}", target_lang)

        updated_terms: list[GlossaryTerm] = []

        for i in range(0, len(terms), max_batch_size):
            batch = terms[i : i + max_batch_size]
            terms_payload = [{"source": t.source, "category": t.category} for t in batch]

            full_prompt = prompt_base.replace(
                "{terms_json}",
                json.dumps(terms_payload, ensure_ascii=False, indent=2),
            )

            req = LLMRequest(
                system_prompt=full_prompt,
                messages=[Message(role="user", content="Translate the terms and return JSON.")],
                temperature=0.1,
                response_schema={"type": "object"},
            )

            data = None
            for attempt in range(2):
                try:
                    resp = await client.complete(req)
                    cleaned = cls._clean_json_response(resp.content)
                    data = json.loads(cleaned)
                    break
                except (POTranslatorError, json.JSONDecodeError, OSError) as e:
                    logger.warning("Glossary translation failed on attempt %d: %s", attempt + 1, e)

            if data is None or not isinstance(data, dict) or "translations" not in data:
                # If translation fails, preserve original term with empty target
                updated_terms.extend(batch)
                continue

            trans_map = {
                item["source"]: item["target"]
                for item in data["translations"]
                if isinstance(item, dict) and "source" in item and "target" in item
            }

            for t in batch:
                target_val = trans_map.get(t.source)
                updated_terms.append(
                    GlossaryTerm(
                        id=t.id,
                        source=t.source,
                        target=target_val if target_val is not None else t.target,
                        category=t.category,
                        description=t.description,
                        locked=t.locked,
                        frequency=t.frequency,
                        created_by=t.created_by,
                    )
                )

        return updated_terms
