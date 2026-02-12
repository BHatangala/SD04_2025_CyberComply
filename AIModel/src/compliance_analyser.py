import json
import re
from typing import Dict, List
from .model_loader import get_model
from .document_processor import DocumentProcessor

class ComplianceAnalyzer:
    def __init__(self):
        self.model = get_model()
        self.processor = DocumentProcessor()
        # In a real app, you'd load this from your data/regulations/ folder
        self.pdpa_requirements = self._load_pdpa_requirements()

    def _load_pdpa_requirements(self) -> List[Dict]:
        """Structure requirements based on Sri Lanka PDPA 2022 Parts"""
        return [
            {
                "id": "SL-PDPA-10",
                "clause": "Conditions for Consent",
                "requirement": "Data controllers must demonstrate that data subjects have given consent to the processing of their personal data.",
                "section": "Section 10"
            },
            {
                "id": "SL-PDPA-12",
                "clause": "Data Minimization",
                "requirement": "Processing must be adequate, relevant and limited to what is necessary in relation to the purposes.",
                "section": "Section 12"
            }
        ]

    def analyze_document(self, document_path: str) -> Dict:
        raw_text = self.processor.extract_text(document_path)
        clean_text = self.processor.preprocess_text(raw_text)
        
        # Optimization: Use the chunking logic we built earlier
        # This prevents the model from being overwhelmed by a huge text wall
        chunks = self.processor.chunk_text(clean_text)
        
        compliance_results = []
        for req in self.pdpa_requirements:
            # For each requirement, we find the most relevant chunk
            # (Simple version: we analyze chunks until we find compliance)
            best_evidence = ""
            for chunk in chunks:
                result = self._check_compliance(chunk, req)
                if result["status"] == "compliant":
                    best_evidence = result
                    break
                best_evidence = result # Keep the last analysis if not compliant
            
            compliance_results.append(best_evidence)

        return {
            "compliance_score": self._calculate_score(compliance_results),
            "details": compliance_results
        }

    def _check_compliance(self, chunk: str, requirement: Dict) -> Dict:
        """AI prompt optimized for DeepSeek R1 4-bit and 2GB VRAM"""
        
        prompt = f"""<SYSTEM>
        You are a Sri Lankan Legal Compliance Officer. Analyze the text below specifically against {requirement['section']} of the PDPA No. 9 of 2022.
        </SYSTEM>
        
        <REQUIREMENT>
        ID: {requirement['id']}
        Clause: {requirement['clause']}
        Requirement: {requirement['requirement']}
        </REQUIREMENT>

        <POLICY_TEXT>
        {chunk}
        </POLICY_TEXT>

        INSTRUCTION: 
        1. Reason through the document.
        2. Provide a JSON object containing: "status", "confidence", "reasoning", and "risk_level".
        
        Format example:
        {{"status": "compliant", "confidence": 90, "reasoning": "...", "risk_level": "low"}}
        """

        raw_response = self.model.generate_response(prompt, max_length=1500, temperature=0.1)
        
        # Optimization: Remove the <think> block and extract JSON
        # DeepSeek-R1's internal reasoning can be huge; we need to strip it to get the JSON.
        cleaned_json = self._extract_json(raw_response)
        
        return {
            "requirement_id": requirement['id'],
            "clause": requirement['clause'],
            **cleaned_json # Merges status, confidence, reasoning, etc.
        }

    def _extract_json(self, text: str) -> Dict:
        """Safety helper to remove <think> tags and parse JSON from DeepSeek"""
        try:
            # 1. Remove the CoT (Chain of Thought) block
            text_no_think = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            
            # 2. Find the first '{' and last '}' to isolate the JSON string
            match = re.search(r'\{.*\}', text_no_think, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"JSON Parsing Error: {e}")
            
        return {
            "status": "error",
            "confidence": 0,
            "reasoning": "Failed to parse AI response.",
            "risk_level": "unknown"
        }

    def _calculate_score(self, results: List[Dict]) -> float:
        if not results: return 0.0
        weights = {"compliant": 100, "partial": 50, "non_compliant": 0, "error": 0}
        total = sum(weights.get(r["status"], 0) for r in results)
        return round(total / len(results), 2)