"""
Haiku Scorer - Low-cost confidence and relevance scoring using Claude Haiku.
"""
import os
import json
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pydantic import BaseModel


class ScoringResult(BaseModel):
    confidence: float  # 0.0 - 1.0
    relevance: float   # 0.0 - 1.0
    reasoning: str
    suggested_tests: List[str] = []


@dataclass
class HaikuScorer:
    """Uses Claude Haiku for low-cost hypothesis scoring."""
    
    api_key: str = None
    model: str = "claude-3-haiku-20240307"
    base_url: str = "https://api.anthropic.com/v1/messages"
    
    def __post_init__(self):
        self.api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        self._mock_mode = not self.api_key
        if self._mock_mode:
            print("[HaikuScorer] No API key found, running in mock mode")
    
    async def score_hypothesis(
        self,
        hypothesis: str,
        evidence: List[Dict[str, Any]],
        context: Optional[str] = None
    ) -> ScoringResult:
        """Score a hypothesis for confidence and relevance."""
        
        if self._mock_mode:
            return self._mock_score(hypothesis, evidence)
        
        prompt = self._build_scoring_prompt(hypothesis, evidence, context)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 500,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                response.raise_for_status()
                result = response.json()
                return self._parse_response(result)
        except Exception as e:
            print(f"[HaikuScorer] API error: {e}, falling back to mock")
            return self._mock_score(hypothesis, evidence)
    
    async def evaluate_evidence(
        self,
        hypothesis: str,
        new_evidence: str,
        existing_confidence: float
    ) -> Dict[str, Any]:
        """Evaluate how new evidence affects hypothesis confidence."""
        
        if self._mock_mode:
            return self._mock_evaluate(hypothesis, new_evidence, existing_confidence)
        
        prompt = f"""Evaluate how this evidence affects the hypothesis.

HYPOTHESIS: {hypothesis}
CURRENT CONFIDENCE: {existing_confidence:.2f}
NEW EVIDENCE: {new_evidence}

Respond in JSON format:
{{
    "supports": true/false,
    "impact": "strong/moderate/weak",
    "new_confidence": 0.0-1.0,
    "explanation": "brief explanation"
}}"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 300,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                response.raise_for_status()
                result = response.json()
                text = result["content"][0]["text"]
                return json.loads(self._extract_json(text))
        except Exception as e:
            print(f"[HaikuScorer] Evaluation error: {e}")
            return self._mock_evaluate(hypothesis, new_evidence, existing_confidence)
    
    async def rank_hypotheses(
        self,
        hypotheses: List[Dict[str, Any]],
        investigation_context: str
    ) -> List[Dict[str, Any]]:
        """Rank multiple hypotheses by investigative value."""
        
        if self._mock_mode or len(hypotheses) == 0:
            return sorted(hypotheses, key=lambda h: h.get("priority", 0), reverse=True)
        
        hypotheses_text = "\n".join([
            f"{i+1}. {h['statement']} (confidence: {h.get('confidence', 0.5):.2f})"
            for i, h in enumerate(hypotheses)
        ])
        
        prompt = f"""Rank these hypotheses by investigative priority.

CONTEXT: {investigation_context}

HYPOTHESES:
{hypotheses_text}

Consider:
- Which hypothesis, if true, would be most significant?
- Which has the best evidence-to-effort ratio?
- Which could unlock other hypotheses?

Respond with a JSON array of hypothesis numbers in priority order:
{{"ranking": [3, 1, 2], "reasoning": "brief explanation"}}"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 300,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                response.raise_for_status()
                result = response.json()
                text = result["content"][0]["text"]
                ranking_data = json.loads(self._extract_json(text))
                
                # Reorder hypotheses based on ranking
                ranking = ranking_data.get("ranking", list(range(1, len(hypotheses) + 1)))
                ranked = []
                for idx in ranking:
                    if 1 <= idx <= len(hypotheses):
                        ranked.append(hypotheses[idx - 1])
                return ranked
        except Exception as e:
            print(f"[HaikuScorer] Ranking error: {e}")
            return sorted(hypotheses, key=lambda h: h.get("priority", 0), reverse=True)
    
    def _build_scoring_prompt(
        self,
        hypothesis: str,
        evidence: List[Dict[str, Any]],
        context: Optional[str]
    ) -> str:
        evidence_text = "\n".join([
            f"- [{e.get('type', 'unknown')}] {e.get('text', e.get('summary', str(e)))}"
            for e in evidence[:10]  # Limit to 10 pieces of evidence
        ])
        
        return f"""Score this investigative hypothesis.

HYPOTHESIS: {hypothesis}

EVIDENCE:
{evidence_text if evidence else "No evidence collected yet"}

{f"CONTEXT: {context}" if context else ""}

Evaluate and respond in JSON format:
{{
    "confidence": 0.0-1.0,  // how likely is this hypothesis true based on evidence
    "relevance": 0.0-1.0,   // how important is this to the investigation
    "reasoning": "2-3 sentences explaining the scores",
    "suggested_tests": ["test 1", "test 2"]  // ways to validate/refute
}}"""
    
    def _parse_response(self, result: Dict) -> ScoringResult:
        try:
            text = result["content"][0]["text"]
            data = json.loads(self._extract_json(text))
            return ScoringResult(
                confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
                relevance=max(0.0, min(1.0, float(data.get("relevance", 0.5)))),
                reasoning=data.get("reasoning", "No reasoning provided"),
                suggested_tests=data.get("suggested_tests", [])
            )
        except Exception as e:
            print(f"[HaikuScorer] Parse error: {e}")
            return ScoringResult(
                confidence=0.5,
                relevance=0.5,
                reasoning="Failed to parse LLM response",
                suggested_tests=[]
            )
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text that might have surrounding content."""
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return text[start:end]
        return text
    
    def _mock_score(self, hypothesis: str, evidence: List[Dict]) -> ScoringResult:
        """Generate mock scores when no API key is available."""
        # Simple heuristic-based scoring
        evidence_count = len(evidence)
        base_confidence = 0.3 + min(0.4, evidence_count * 0.1)
        
        # Check for investigative keywords
        keywords = ["unusual", "pattern", "connection", "anomaly", "spike"]
        relevance_boost = sum(0.1 for k in keywords if k in hypothesis.lower())
        base_relevance = 0.5 + min(0.3, relevance_boost)
        
        return ScoringResult(
            confidence=base_confidence,
            relevance=base_relevance,
            reasoning=f"[Mock] Hypothesis has {evidence_count} pieces of evidence. "
                     f"Scored based on keyword analysis.",
            suggested_tests=[
                "Search for additional corroborating evidence",
                "Check for contradicting data points",
                "Verify source credibility"
            ]
        )
    
    def _mock_evaluate(
        self,
        hypothesis: str,
        new_evidence: str,
        existing_confidence: float
    ) -> Dict[str, Any]:
        """Mock evidence evaluation."""
        # Simple heuristic
        supports = "confirm" in new_evidence.lower() or "found" in new_evidence.lower()
        impact = 0.1 if supports else -0.05
        
        return {
            "supports": supports,
            "impact": "moderate",
            "new_confidence": max(0.0, min(1.0, existing_confidence + impact)),
            "explanation": f"[Mock] Evidence {'supports' if supports else 'weakens'} hypothesis"
        }
