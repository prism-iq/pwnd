"""
Hypothesis Generator - Creates investigative hypotheses from entities and patterns.
"""
import os
import json
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class HypothesisType(str, Enum):
    CONNECTION = "connection"      # Two entities are related
    ANOMALY = "anomaly"           # Something unusual detected
    PATTERN = "pattern"           # Recurring pattern found
    CAUSATION = "causation"       # X caused Y
    TEMPORAL = "temporal"         # Time-based correlation


@dataclass
class GeneratedHypothesis:
    statement: str
    hypothesis_type: HypothesisType
    test_description: str
    initial_confidence: float
    initial_relevance: float
    source_entities: List[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass 
class HypothesisGenerator:
    """Generates investigative hypotheses from extracted data."""
    
    api_key: str = None
    model: str = "claude-3-haiku-20240307"
    base_url: str = "https://api.anthropic.com/v1/messages"
    
    def __post_init__(self):
        self.api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        self._mock_mode = not self.api_key
    
    async def generate_from_entities(
        self,
        entities: List[Dict[str, Any]],
        context: Optional[str] = None,
        max_hypotheses: int = 5
    ) -> List[GeneratedHypothesis]:
        """Generate hypotheses from a set of extracted entities."""
        
        if not entities:
            return []
        
        if self._mock_mode:
            return self._mock_generate_from_entities(entities, max_hypotheses)
        
        entities_text = self._format_entities(entities)
        
        prompt = f"""Analyze these entities extracted from an investigation and generate investigative hypotheses.

ENTITIES:
{entities_text}

{f"INVESTIGATION CONTEXT: {context}" if context else ""}

Generate {max_hypotheses} hypotheses that could explain connections, patterns, or anomalies.
Each hypothesis should be:
1. Specific and testable
2. Based on the entities provided
3. Useful for advancing the investigation

Respond in JSON format:
{{
    "hypotheses": [
        {{
            "statement": "clear hypothesis statement",
            "type": "connection|anomaly|pattern|causation|temporal",
            "test": "how to validate or refute this",
            "confidence": 0.0-1.0,
            "relevance": 0.0-1.0,
            "entities": ["entity1", "entity2"],
            "reasoning": "why this hypothesis matters"
        }}
    ]
}}"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 1500,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                response.raise_for_status()
                result = response.json()
                return self._parse_hypotheses(result)
        except Exception as e:
            print(f"[HypothesisGenerator] API error: {e}")
            return self._mock_generate_from_entities(entities, max_hypotheses)
    
    async def generate_from_anomaly(
        self,
        anomaly_description: str,
        related_data: Dict[str, Any],
        context: Optional[str] = None
    ) -> List[GeneratedHypothesis]:
        """Generate hypotheses to explain a detected anomaly."""
        
        if self._mock_mode:
            return [GeneratedHypothesis(
                statement=f"Anomaly '{anomaly_description}' indicates unusual activity",
                hypothesis_type=HypothesisType.ANOMALY,
                test_description="Investigate time period around anomaly for corroborating events",
                initial_confidence=0.4,
                initial_relevance=0.7,
                reasoning="[Mock] Anomalies often indicate significant events"
            )]
        
        prompt = f"""An anomaly was detected in the investigation data.

ANOMALY: {anomaly_description}

RELATED DATA:
{json.dumps(related_data, indent=2, default=str)[:1000]}

{f"CONTEXT: {context}" if context else ""}

Generate 2-3 hypotheses that could explain this anomaly.

Respond in JSON:
{{
    "hypotheses": [
        {{
            "statement": "explanation for the anomaly",
            "type": "anomaly",
            "test": "how to validate",
            "confidence": 0.0-1.0,
            "relevance": 0.0-1.0,
            "reasoning": "why this explanation makes sense"
        }}
    ]
}}"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 800,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                response.raise_for_status()
                result = response.json()
                return self._parse_hypotheses(result)
        except Exception as e:
            print(f"[HypothesisGenerator] Anomaly generation error: {e}")
            return []
    
    async def generate_followup(
        self,
        original_hypothesis: str,
        test_result: str,
        was_supported: bool
    ) -> List[GeneratedHypothesis]:
        """Generate follow-up hypotheses based on test results."""
        
        if self._mock_mode:
            action = "confirmed" if was_supported else "refuted"
            return [GeneratedHypothesis(
                statement=f"Given {action} hypothesis, investigate related factors",
                hypothesis_type=HypothesisType.CONNECTION,
                test_description="Search for additional connections",
                initial_confidence=0.5,
                initial_relevance=0.6,
                reasoning=f"[Mock] Follow-up to {action} hypothesis"
            )]
        
        prompt = f"""A hypothesis was tested in an investigation.

ORIGINAL HYPOTHESIS: {original_hypothesis}
TEST RESULT: {test_result}
OUTCOME: {"Supported" if was_supported else "Refuted"}

Based on this outcome, generate 2-3 follow-up hypotheses to continue the investigation.

Respond in JSON:
{{
    "hypotheses": [
        {{
            "statement": "follow-up hypothesis",
            "type": "connection|anomaly|pattern|causation|temporal",
            "test": "how to test this",
            "confidence": 0.0-1.0,
            "relevance": 0.0-1.0,
            "reasoning": "why investigate this next"
        }}
    ]
}}"""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 800,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                response.raise_for_status()
                result = response.json()
                return self._parse_hypotheses(result)
        except Exception as e:
            print(f"[HypothesisGenerator] Follow-up error: {e}")
            return []
    
    def _format_entities(self, entities: List[Dict[str, Any]]) -> str:
        """Format entities for prompt."""
        lines = []
        for e in entities[:20]:  # Limit to 20 entities
            entity_type = e.get("type", e.get("label", "unknown"))
            value = e.get("value", e.get("name", e.get("canonical_name", str(e))))
            confidence = e.get("confidence", "N/A")
            lines.append(f"- [{entity_type}] {value} (confidence: {confidence})")
        return "\n".join(lines)
    
    def _parse_hypotheses(self, result: Dict) -> List[GeneratedHypothesis]:
        """Parse LLM response into hypothesis objects."""
        try:
            text = result["content"][0]["text"]
            # Extract JSON
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(text[start:end])
            else:
                return []
            
            hypotheses = []
            for h in data.get("hypotheses", []):
                try:
                    h_type = h.get("type", "pattern")
                    if h_type not in [t.value for t in HypothesisType]:
                        h_type = "pattern"
                    
                    hypotheses.append(GeneratedHypothesis(
                        statement=h.get("statement", ""),
                        hypothesis_type=HypothesisType(h_type),
                        test_description=h.get("test", ""),
                        initial_confidence=max(0.0, min(1.0, float(h.get("confidence", 0.5)))),
                        initial_relevance=max(0.0, min(1.0, float(h.get("relevance", 0.5)))),
                        source_entities=h.get("entities", []),
                        reasoning=h.get("reasoning", "")
                    ))
                except Exception as e:
                    print(f"[HypothesisGenerator] Parse single hypothesis error: {e}")
                    continue
            
            return hypotheses
        except Exception as e:
            print(f"[HypothesisGenerator] Parse error: {e}")
            return []
    
    def _mock_generate_from_entities(
        self,
        entities: List[Dict[str, Any]],
        max_hypotheses: int
    ) -> List[GeneratedHypothesis]:
        """Generate mock hypotheses for testing."""
        hypotheses = []
        
        # Group entities by type
        by_type = {}
        for e in entities:
            t = e.get("type", e.get("label", "unknown")).lower()
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        # Generate connection hypotheses between entity types
        types = list(by_type.keys())
        for i, t1 in enumerate(types[:3]):
            for t2 in types[i+1:3]:
                if by_type[t1] and by_type[t2]:
                    e1 = by_type[t1][0]
                    e2 = by_type[t2][0]
                    v1 = e1.get("value", e1.get("name", str(e1)))
                    v2 = e2.get("value", e2.get("name", str(e2)))
                    
                    hypotheses.append(GeneratedHypothesis(
                        statement=f"{v1} ({t1}) may be connected to {v2} ({t2})",
                        hypothesis_type=HypothesisType.CONNECTION,
                        test_description=f"Search for communications or events linking {v1} and {v2}",
                        initial_confidence=0.4,
                        initial_relevance=0.6,
                        source_entities=[v1, v2],
                        reasoning=f"[Mock] Co-occurrence of {t1} and {t2} entities suggests potential relationship"
                    ))
                    
                    if len(hypotheses) >= max_hypotheses:
                        break
            if len(hypotheses) >= max_hypotheses:
                break
        
        # Add a pattern hypothesis if we have timestamps
        if "date" in by_type and len(by_type["date"]) > 1:
            hypotheses.append(GeneratedHypothesis(
                statement="Multiple date references suggest a timeline of significant events",
                hypothesis_type=HypothesisType.TEMPORAL,
                test_description="Create timeline and identify event clustering",
                initial_confidence=0.5,
                initial_relevance=0.7,
                source_entities=[d.get("value", "") for d in by_type["date"][:3]],
                reasoning="[Mock] Multiple dates often indicate a sequence of related events"
            ))
        
        return hypotheses[:max_hypotheses]
