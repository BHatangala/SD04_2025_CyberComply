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
    # 4. ORG CONTEXT BLOCK BUILDER
    # ──────────────────────────────────────────────
    def _build_org_context(self, org_name: str, department: str) -> str:
        """Build the <ORGANISATION_CONTEXT> block injected into every batch prompt.

        If neither org_name nor department is provided (e.g. non-admin upload),
        returns an empty string so the prompt is identical to the previous behaviour.
        """
        if not org_name and not department:
            return ''

        org_line  = f"Organisation: {org_name}" if org_name else "Organisation: Unknown"
        dept_line = f"Department:   {department}" if department else ""
        context_lines = [org_line]
        if dept_line:
            context_lines.append(dept_line)

        context_body = "\n".join(context_lines)

        return f"""<ORGANISATION_CONTEXT>
{context_body}

Using the organisation name and department above, infer the likely industry
sector (e.g. Banking & Finance, Healthcare, IT & Technology, Retail, etc.)
and the categories of personal data this department is most likely to process.

Apply this sector understanding in two ways:

1. RISK_LEVEL — Calibrate severity to reflect the sector's actual exposure.
   High-sensitivity sectors (banking, healthcare, telecoms, legal) that handle
   financial records, health data, or identity documents should have RISK_LEVEL
   elevated where a gap is particularly damaging for that sector. Lower-risk
   sectors may have the same gap assessed at a lower severity. The base
   Risk Weight provided per requirement is the floor — elevate where the sector
   justifies it, do not lower below it.

2. REASONING — At the end of your reasoning for any non_compliant or partial
   finding, add exactly one sentence explaining why this specific gap is
   especially significant (or less so) for this type of organisation and
   department. Keep this sentence concise and sector-specific.

IMPORTANT: Do NOT change the compliance STATUS (compliant/partial/non_compliant)
based on sector context. Status is determined solely by what the policy text
explicitly states or omits.
</ORGANISATION_CONTEXT>

"""

    # ──────────────────────────────────────────────
    # 5. MAIN ANALYSIS ENTRY POINT
    # ──────────────────────────────────────────────
    def analyze_document(
        self,
        document_path: str,
        org_name: str = '',
        department: str = '',
    ) -> Dict:
        raw_text   = self.processor.extract_text(document_path)
        clean_text = self.processor.preprocess_text(raw_text)
        chunks     = self.processor.chunk_text(clean_text)

        # Send the first 3 chunks as a single representative block.
        # This gives the model enough context without overwhelming the prompt.
        # Hard-capped at 6000 chars (~1 500 tokens) to stay well inside the
        # 32 K context window after adding the requirements text.
        representative_chunk = "\n\n---\n\n".join(chunks[:3])[:6000]

        # Build the org context block once — reused across every batch.
        org_context = self._build_org_context(org_name, department)
        if org_context:
            print(f"[INFO] Organisation context active — org: '{org_name}', dept: '{department}'")
        else:
            print(f"[INFO] No organisation context provided — generic analysis mode")

        batches = self._batch_requirements(self.pdpa_requirements, batch_size=6)
        total   = len(self.pdpa_requirements)
        print(f"[INFO] Starting analysis: {total} requirements across {len(batches)} batches")

        all_results = []
        for i, batch in enumerate(batches):
            print(f"[INFO] Batch {i+1}/{len(batches)} — checking {len(batch)} requirements...")
            batch_results = self._check_compliance_batch(
                representative_chunk, batch, org_context
            )
            all_results.extend(batch_results)

            # Courtesy delay between batches — keeps requests well under the
            # 20 req/min free-tier limit and avoids 429s proactively.
            # 10s gap also helps when routing through fallback models with tighter limits.
            if i < len(batches) - 1:
                time.sleep(10)

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
    # 6. BATCH COMPLIANCE CHECK (one API call)
    # ──────────────────────────────────────────────
    def _check_compliance_batch(
        self,
        chunk: str,
        requirements: List[Dict],
        org_context: str = '',
    ) -> List[Dict]:
        """Send one document chunk + N requirements in a single API call."""

        req_blocks = [self._format_requirement_for_prompt(r) for r in requirements]
        requirements_text = "\n\n---\n\n".join(req_blocks)
        req_ids = [r["id"] for r in requirements]

        prompt = f"""<s>
You are a Sri Lankan Legal Compliance Officer. Analyze the POLICY TEXT below against
MULTIPLE requirements from the Personal Data Protection Act No. 9 of 2022.
</s>
 
{org_context}<REQUIREMENTS_TO_CHECK>
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
  "clause"          — copy the "clause_title" field value without prepending any section numbers or any "Section X" prefix
  "status"          — one of: compliant | partial | non_compliant
  "confidence"      — integer 0-100
  "reasoning"       — 2-3 sentences explaining the finding (if non_compliant or partial,
                      end with one sentence on why this gap is significant for the
                      specific organisation and department provided above)
  "risk_level"      — one of: low | medium | high | critical
                      (calibrated to the organisation's sector — see ORGANISATION_CONTEXT)
 
Return ONLY the JSON array. No preamble, no explanation outside the array.
"""

        print(f"[DEBUG] Sending batch to model — requirements: {req_ids}")
        print(f"[DEBUG] Prompt length: {len(prompt)} chars")

        # Minimum viable response length: each object needs ~350 chars minimum
        # (reasoning alone averages 200+ chars; status/clause/confidence add more).
        # If the response is shorter, the model was cut off mid-array and parsing
        # will fail — retry once with a short pause before falling back to errors.
        min_expected_chars = len(requirements) * 350

        raw_response = self.model.generate_response(prompt, max_length=4000, temperature=0.1)

        if len(raw_response) < min_expected_chars:
            print(f"[WARN] Response too short ({len(raw_response)} chars, expected >{min_expected_chars}). Retrying batch...")
            time.sleep(5)
            raw_response = self.model.generate_response(prompt, max_length=4000, temperature=0.1)

        print(f"[DEBUG] Raw response preview: {raw_response[:300]}")

        return self._extract_json_array(raw_response, requirements, prompt)

    # ──────────────────────────────────────────────
    # 7. RESPONSE PARSER
    # ──────────────────────────────────────────────
    def _extract_json_array(self, text: str, requirements: List[Dict], prompt: str = '') -> List[Dict]:
        """Strip DeepSeek <think> tags and parse the JSON array.

        Handles three common failure modes from free/fallback models:
          1. Metadata wrapper — openrouter/free sometimes prepends the raw API
             JSON body which contains brackets before the requirements array.
             Fixed by finding the [...] block that contains "requirement_id".
          2. Truncated response — json.loads fails on an incomplete array;
             retry once, then salvage any complete individual objects.
          3. Markdown fences — some models wrap output in ```json ... ```;
             stripped before searching.
        """
        try:
            # Remove chain-of-thought block that DeepSeek R1 emits
            text_clean = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

            # Strip markdown fences that some free models wrap output in
            text_clean = re.sub(r'```(?:json)?\s*', '', text_clean).strip()

            # Find ALL [...] blocks, then pick the one that:
            #   a) contains "requirement_id" (uniquely identifies our array), AND
            #   b) is the longest such block (most complete response).
            # This avoids false matches on OpenRouter metadata brackets that some
            # models prepend to their response.
            all_matches = list(re.finditer(r'\[.*\]', text_clean, re.DOTALL))
            best_match = None
            for m in all_matches:
                if 'requirement_id' in m.group():
                    if best_match is None or len(m.group()) > len(best_match.group()):
                        best_match = m
            # Last resort: use the final [...] block if none contain requirement_id
            match = best_match or (all_matches[-1] if all_matches else None)

            if match:
                try:
                    parsed = json.loads(match.group())
                    # Validate it's actually our requirements array, not metadata
                    if isinstance(parsed, list) and len(parsed) > 0 and parsed[0].get("requirement_id"):
                        print(f"[DEBUG] Parsed {len(parsed)} results from batch response")
                        parsed = [{**r, "clause": self._strip_section_prefix(r["clause"])} if r.get("clause") else r for r in parsed]
                        return parsed
                except json.JSONDecodeError as e:
                    # Full parse failed — likely mid-sentence truncation on the last
                    # object. Retry once with a short pause before falling to salvage.
                    print(f"[WARN] Full JSON array parse failed: {e}. Retrying batch once...")
                    if prompt:
                        time.sleep(5)
                        retry_resp = self.model.generate_response(prompt, max_length=4000, temperature=0.1)
                        try:
                            rc = re.sub(r'<think>.*?</think>', '', retry_resp, flags=re.DOTALL)
                            rc = re.sub(r'```(?:json)?\s*', '', rc).strip()
                            rm_all = list(re.finditer(r'\[.*\]', rc, re.DOTALL))
                            rm_best = None
                            for m in rm_all:
                                if 'requirement_id' in m.group():
                                    if rm_best is None or len(m.group()) > len(rm_best.group()):
                                        rm_best = m
                            rm = rm_best or (rm_all[-1] if rm_all else None)
                            if rm:
                                rp = json.loads(rm.group())
                                if isinstance(rp, list) and len(rp) > 0 and rp[0].get("requirement_id"):
                                    print(f"[DEBUG] Retry succeeded — parsed {len(rp)} results")
                                    rp = [{**r, "clause": ComplianceAnalyzer._strip_section_prefix(r["clause"])} if r.get("clause") else r for r in rp]
                                    return rp
                        except Exception:
                            pass  # Retry also failed — fall through to salvage

                    # Salvage: extract any individually complete {...} objects
                    salvaged = []
                    for obj_match in re.finditer(r'\{[^{}]*"requirement_id"[^{}]*\}', match.group(), re.DOTALL):
                        try:
                            obj = json.loads(obj_match.group())
                            if obj.get("requirement_id"):
                                obj["clause"] = self._strip_section_prefix(obj.get("clause", ""))
                                salvaged.append(obj)
                        except json.JSONDecodeError:
                            continue
                    if salvaged:
                        print(f"[WARN] Salvaged {len(salvaged)}/{len(requirements)} objects from truncated response")
                        salvaged_ids = {o["requirement_id"] for o in salvaged}
                        for req in requirements:
                            if req["id"] not in salvaged_ids:
                                salvaged.append({
                                    "requirement_id": req["id"],
                                    "clause": req.get("clause_title", req.get("clause", "Unknown")),
                                    "status": "error",
                                    "confidence": 0,
                                    "reasoning": "Response was truncated before this requirement was evaluated.",
                                    "risk_level": req.get("risk_weight", "unknown")
                                })
                        return salvaged

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
    # 8. SCORE CALCULATOR (unchanged logic)
    # ──────────────────────────────────────────────
    def _calculate_score(self, results: List[Dict]) -> float:
        if not results:
            return 0.0
        weights = {"compliant": 100, "partial": 50, "non_compliant": 0, "error": 0}
        total = sum(weights.get(r.get("status", "error"), 0) for r in results)
        return round(total / len(results), 2)

    # ──────────────────────────────────────────────
    # 9. CLAUSE SANITISER
    # ──────────────────────────────────────────────
    @staticmethod
    def _strip_section_prefix(clause: str) -> str:
        """Remove any leading 'Section X(Y) — ' or 'Section X ' the model adds."""
        return re.sub(r'^Section\s+[\d]+(?:\(\d+\))?\s*[\-—–]?\s*', '', clause).strip()