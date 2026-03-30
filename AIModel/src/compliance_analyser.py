import json
import re
import os
import time
from typing import Dict, List, Optional
from .model_loader import get_model
from .document_processor import DocumentProcessor


class ComplianceAnalyzer:
    def __init__(self, requirements_path: Optional[str] = None):
        self.model = get_model()
        self.processor = DocumentProcessor()
        self.pdpa_requirements = self._load_pdpa_requirements(requirements_path)

    # ──────────────────────────────────────────────
    # 1. LOAD FROM JSON (replaces hardcoded list)
    # ──────────────────────────────────────────────
    def _load_pdpa_requirements(self, path: Optional[str] = None) -> List[Dict]:
        """Load all PDPA requirements from JSON file."""
        if path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base_dir, "data", "regulations", "pdpa_requirements_full.json")

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"PDPA requirements file not found at: {path}\n"
                "Place pdpa_requirements_full.json in data/regulations/ or pass the path explicitly."
            )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        requirements = data.get("requirements", [])
        print(f"[INFO] Loaded {len(requirements)} PDPA requirements from {path}")
        return requirements

    # ──────────────────────────────────────────────
    # 2. FORMAT ONE REQUIREMENT FOR PROMPT
    # ──────────────────────────────────────────────
    def _format_requirement_for_prompt(self, req: Dict) -> str:
        """Flatten a requirement (including schedule_content) into prompt text."""
        section_str = str(req.get("section", ""))
        if req.get("subsection"):
            section_str += f"({req['subsection']})"

        lines = [
            f"ID: {req['id']}",
            f"Section: {section_str}",
            f"Clause: {req.get('clause_title', req.get('clause', 'N/A'))}",
            f"Requirement: {req['requirement']}",
            f"Risk Weight: {req.get('risk_weight', 'medium')}",
        ]

        if req.get("keywords"):
            lines.append(f"Keywords: {', '.join(req['keywords'])}")

        # Include schedule conditions if present (e.g. Section 5's four schedules)
        if req.get("schedule_content"):
            lines.append("Relevant Schedule Conditions:")
            for sched_name, sched_data in req["schedule_content"].items():
                lines.append(f"  {sched_name}: {sched_data.get('description', '')}")
                for condition in sched_data.get("conditions", [])[:3]:   # first 3 only
                    lines.append(f"    - {condition[:200]}")              # cap length

        return "\n".join(lines)

    # ──────────────────────────────────────────────
    # 3. BATCH SPLITTER
    # ──────────────────────────────────────────────
    def _batch_requirements(self, requirements: List[Dict], batch_size: int = 6) -> List[List[Dict]]:
        return [requirements[i:i + batch_size] for i in range(0, len(requirements), batch_size)]

    # ──────────────────────────────────────────────
    # 4. MAIN ANALYSIS ENTRY POINT
    #    (same signature as before — api_server.py unchanged)
    # ──────────────────────────────────────────────
    def analyze_document(self, document_path: str) -> Dict:
        raw_text  = self.processor.extract_text(document_path)
        clean_text = self.processor.preprocess_text(raw_text)
        chunks    = self.processor.chunk_text(clean_text)

        # Send the first 3 chunks as a single representative block.
        # This gives the model enough context without overwhelming the prompt.
        # Hard-capped at 6000 chars (~1 500 tokens) to stay well inside the
        # 32 K context window after adding the requirements text.
        representative_chunk = "\n\n---\n\n".join(chunks[:3])[:6000]

        batches = self._batch_requirements(self.pdpa_requirements, batch_size=6)
        total   = len(self.pdpa_requirements)
        print(f"[INFO] Starting analysis: {total} requirements across {len(batches)} batches")

        all_results = []
        for i, batch in enumerate(batches):
            print(f"[INFO] Batch {i+1}/{len(batches)} — checking {len(batch)} requirements...")
            batch_results = self._check_compliance_batch(representative_chunk, batch)
            all_results.extend(batch_results)

            # Courtesy delay between batches — keeps requests well under the
            # 20 req/min free-tier limit and avoids 429s proactively.
            if i < len(batches) - 1:
                time.sleep(3)

        score = self._calculate_score(all_results)
        print(f"[INFO] Analysis complete — Compliance Score: {score}%")

        # ── Terminal summary (mirrors what the UI shows) ──
        non_compliant = [r for r in all_results if r.get("status") in ("non_compliant", "partial")]
        print(f"[INFO] Issues found: {len(non_compliant)}/{total} requirements flagged")
        for r in non_compliant:
            print(f"  [{r.get('status','?').upper()}] {r.get('requirement_id','?')} — {r.get('clause','?')}")
            print(f"         {r.get('reasoning','')[:120]}...")

        # Return shape is IDENTICAL to the original so api_server.py and the
        # HTML localStorage consumer both keep working without any changes.
        return {
            "compliance_score": score,
            "total_requirements": total,
            "details": all_results          # List[Dict] — same keys as before
        }

    # ──────────────────────────────────────────────
    # 5. BATCH COMPLIANCE CHECK (one API call)
    # ──────────────────────────────────────────────
    def _check_compliance_batch(self, chunk: str, requirements: List[Dict]) -> List[Dict]:
        """Send one document chunk + N requirements in a single API call."""

        req_blocks = [self._format_requirement_for_prompt(r) for r in requirements]
        requirements_text = "\n\n---\n\n".join(req_blocks)
        req_ids = [r["id"] for r in requirements]

        prompt = f"""<SYSTEM>
You are a Sri Lankan Legal Compliance Officer. Analyze the POLICY TEXT below against
MULTIPLE requirements from the Personal Data Protection Act No. 9 of 2022.
</SYSTEM>

<REQUIREMENTS_TO_CHECK>
{requirements_text}
</REQUIREMENTS_TO_CHECK>

<POLICY_TEXT>
{chunk}
</POLICY_TEXT>

INSTRUCTION:
Analyze the policy text against EACH of the {len(requirements)} requirements above.
Return a JSON ARRAY with exactly {len(requirements)} objects in this order: {req_ids}

Each object MUST contain these keys:
  "requirement_id"  — copy from the ID field above
  "clause"          — copy from the Clause field above
  "status"          — one of: compliant | partial | non_compliant
  "confidence"      — integer 0-100
  "reasoning"       — 2-3 sentences explaining the finding
  "risk_level"      — one of: low | medium | high | critical

Return ONLY the JSON array. No preamble, no explanation outside the array.
"""

        print(f"[DEBUG] Sending batch to model — requirements: {req_ids}")
        print(f"[DEBUG] Prompt length: {len(prompt)} chars")

        raw_response = self.model.generate_response(prompt, max_length=2000, temperature=0.1)

        print(f"[DEBUG] Raw response preview: {raw_response[:300]}")

        return self._extract_json_array(raw_response, requirements)

    # ──────────────────────────────────────────────
    # 6. RESPONSE PARSER
    # ──────────────────────────────────────────────
    def _extract_json_array(self, text: str, requirements: List[Dict]) -> List[Dict]:
        """Strip DeepSeek <think> tags and parse the JSON array."""
        try:
            # Remove chain-of-thought block that DeepSeek R1 emits
            text_clean = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

            # Isolate the JSON array
            match = re.search(r'\[.*\]', text_clean, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                if isinstance(parsed, list) and len(parsed) > 0:
                    print(f"[DEBUG] Parsed {len(parsed)} results from batch response")
                    return parsed

        except Exception as e:
            print(f"[WARN] JSON array parse failed: {e}")
            print(f"[WARN] Offending text snippet: {text[:400]}")

        # Fallback — return safe error entries so the UI never breaks
        print(f"[WARN] Using fallback error entries for batch: {[r['id'] for r in requirements]}")
        return [
            {
                "requirement_id": req["id"],
                "clause": req.get("clause_title", req.get("clause", "Unknown")),
                "status": "error",
                "confidence": 0,
                "reasoning": "Failed to parse AI response for this requirement.",
                "risk_level": req.get("risk_weight", "unknown")
            }
            for req in requirements
        ]

    # ──────────────────────────────────────────────
    # 7. SCORE CALCULATOR (unchanged logic)
    # ──────────────────────────────────────────────
    def _calculate_score(self, results: List[Dict]) -> float:
        if not results:
            return 0.0
        weights = {"compliant": 100, "partial": 50, "non_compliant": 0, "error": 0}
        total = sum(weights.get(r.get("status", "error"), 0) for r in results)
        return round(total / len(results), 2)