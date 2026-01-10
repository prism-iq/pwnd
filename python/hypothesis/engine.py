"""
Hypothesis Engine - Main orchestrator for hypothesis-driven investigation.
"""
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from .scorer import HaikuScorer, ScoringResult
from .generator import HypothesisGenerator, GeneratedHypothesis, HypothesisType


@dataclass
class Hypothesis:
    """A tracked hypothesis in an investigation."""
    id: str
    statement: str
    hypothesis_type: str
    status: str  # pending, testing, supported, refuted, inconclusive
    confidence: float
    relevance: float
    test_description: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    evaluations: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def priority(self) -> float:
        return self.confidence * self.relevance


@dataclass
class Investigation:
    """Container for an investigation with multiple hypotheses."""
    id: str
    name: str
    description: str
    hypotheses: List[Hypothesis] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "active"
    created_at: datetime = field(default_factory=datetime.now)


class HypothesisEngine:
    """
    Main engine for hypothesis-driven investigation.
    
    Uses Haiku for low-cost scoring and evaluation of hypotheses.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.scorer = HaikuScorer(api_key=api_key)
        self.generator = HypothesisGenerator(api_key=api_key)
        self.investigations: Dict[str, Investigation] = {}
    
    async def create_investigation(
        self,
        name: str,
        description: str = "",
        initial_entities: Optional[List[Dict[str, Any]]] = None
    ) -> Investigation:
        """Create a new investigation."""
        inv = Investigation(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            entities=initial_entities or []
        )
        self.investigations[inv.id] = inv
        
        # Auto-generate initial hypotheses if entities provided
        if initial_entities:
            await self.generate_hypotheses(inv.id, context=description)
        
        return inv
    
    async def add_entities(
        self,
        investigation_id: str,
        entities: List[Dict[str, Any]],
        auto_generate: bool = True
    ) -> Investigation:
        """Add entities to an investigation and optionally generate new hypotheses."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        inv.entities.extend(entities)
        
        if auto_generate:
            await self.generate_hypotheses(investigation_id)
        
        return inv
    
    async def generate_hypotheses(
        self,
        investigation_id: str,
        context: Optional[str] = None,
        max_hypotheses: int = 5
    ) -> List[Hypothesis]:
        """Generate new hypotheses for an investigation."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        # Generate hypotheses from entities
        generated = await self.generator.generate_from_entities(
            entities=inv.entities,
            context=context or inv.description,
            max_hypotheses=max_hypotheses
        )
        
        new_hypotheses = []
        for g in generated:
            h = Hypothesis(
                id=str(uuid.uuid4()),
                statement=g.statement,
                hypothesis_type=g.hypothesis_type.value,
                status="pending",
                confidence=g.initial_confidence,
                relevance=g.initial_relevance,
                test_description=g.test_description
            )
            inv.hypotheses.append(h)
            new_hypotheses.append(h)
        
        return new_hypotheses
    
    async def score_hypothesis(
        self,
        investigation_id: str,
        hypothesis_id: str,
        additional_context: Optional[str] = None
    ) -> Hypothesis:
        """Score/rescore a hypothesis using Haiku."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        hypothesis = next((h for h in inv.hypotheses if h.id == hypothesis_id), None)
        if not hypothesis:
            raise ValueError(f"Hypothesis {hypothesis_id} not found")
        
        # Score with Haiku
        result = await self.scorer.score_hypothesis(
            hypothesis=hypothesis.statement,
            evidence=hypothesis.evidence,
            context=additional_context or inv.description
        )
        
        # Update hypothesis
        hypothesis.confidence = result.confidence
        hypothesis.relevance = result.relevance
        hypothesis.updated_at = datetime.now()
        
        # Store evaluation
        hypothesis.evaluations.append({
            "timestamp": datetime.now().isoformat(),
            "confidence": result.confidence,
            "relevance": result.relevance,
            "reasoning": result.reasoning,
            "suggested_tests": result.suggested_tests
        })
        
        return hypothesis
    
    async def add_evidence(
        self,
        investigation_id: str,
        hypothesis_id: str,
        evidence: Dict[str, Any],
        auto_rescore: bool = True
    ) -> Hypothesis:
        """Add evidence to a hypothesis and optionally rescore."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        hypothesis = next((h for h in inv.hypotheses if h.id == hypothesis_id), None)
        if not hypothesis:
            raise ValueError(f"Hypothesis {hypothesis_id} not found")
        
        # Add evidence
        evidence["added_at"] = datetime.now().isoformat()
        hypothesis.evidence.append(evidence)
        hypothesis.updated_at = datetime.now()
        
        # Evaluate impact of new evidence
        if auto_rescore:
            eval_result = await self.scorer.evaluate_evidence(
                hypothesis=hypothesis.statement,
                new_evidence=evidence.get("text", evidence.get("summary", str(evidence))),
                existing_confidence=hypothesis.confidence
            )
            
            hypothesis.confidence = eval_result.get("new_confidence", hypothesis.confidence)
            hypothesis.evaluations.append({
                "timestamp": datetime.now().isoformat(),
                "type": "evidence_update",
                "evidence_id": evidence.get("id"),
                "supports": eval_result.get("supports"),
                "impact": eval_result.get("impact"),
                "explanation": eval_result.get("explanation")
            })
        
        return hypothesis
    
    async def test_hypothesis(
        self,
        investigation_id: str,
        hypothesis_id: str,
        test_result: str,
        outcome: str  # "supported", "refuted", "inconclusive"
    ) -> Dict[str, Any]:
        """Record a hypothesis test result and generate follow-ups."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        hypothesis = next((h for h in inv.hypotheses if h.id == hypothesis_id), None)
        if not hypothesis:
            raise ValueError(f"Hypothesis {hypothesis_id} not found")
        
        # Update status
        hypothesis.status = outcome
        hypothesis.updated_at = datetime.now()
        
        # Adjust confidence based on outcome
        if outcome == "supported":
            hypothesis.confidence = min(1.0, hypothesis.confidence + 0.2)
        elif outcome == "refuted":
            hypothesis.confidence = max(0.0, hypothesis.confidence - 0.3)
        
        # Store test result
        hypothesis.evaluations.append({
            "timestamp": datetime.now().isoformat(),
            "type": "test_result",
            "test_result": test_result,
            "outcome": outcome
        })
        
        # Generate follow-up hypotheses
        followups = await self.generator.generate_followup(
            original_hypothesis=hypothesis.statement,
            test_result=test_result,
            was_supported=(outcome == "supported")
        )
        
        new_hypotheses = []
        for f in followups:
            h = Hypothesis(
                id=str(uuid.uuid4()),
                statement=f.statement,
                hypothesis_type=f.hypothesis_type.value,
                status="pending",
                confidence=f.initial_confidence,
                relevance=f.initial_relevance,
                test_description=f.test_description
            )
            inv.hypotheses.append(h)
            new_hypotheses.append(h)
        
        return {
            "updated_hypothesis": hypothesis,
            "followup_hypotheses": new_hypotheses
        }
    
    async def get_ranked_hypotheses(
        self,
        investigation_id: str,
        status_filter: Optional[str] = None,
        limit: int = 10
    ) -> List[Hypothesis]:
        """Get hypotheses ranked by priority (confidence * relevance)."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        hypotheses = inv.hypotheses
        
        if status_filter:
            hypotheses = [h for h in hypotheses if h.status == status_filter]
        
        # Use Haiku to rank if we have an API key
        if not self.scorer._mock_mode and len(hypotheses) > 1:
            hypothesis_dicts = [
                {
                    "id": h.id,
                    "statement": h.statement,
                    "confidence": h.confidence,
                    "relevance": h.relevance,
                    "priority": h.priority
                }
                for h in hypotheses
            ]
            ranked_dicts = await self.scorer.rank_hypotheses(
                hypotheses=hypothesis_dicts,
                investigation_context=inv.description
            )
            # Reorder hypotheses based on ranking
            id_order = [d["id"] for d in ranked_dicts]
            hypotheses = sorted(hypotheses, key=lambda h: id_order.index(h.id) if h.id in id_order else 999)
        else:
            hypotheses = sorted(hypotheses, key=lambda h: h.priority, reverse=True)
        
        return hypotheses[:limit]
    
    async def analyze_investigation(
        self,
        investigation_id: str
    ) -> Dict[str, Any]:
        """Get a comprehensive analysis of the investigation state."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            raise ValueError(f"Investigation {investigation_id} not found")
        
        # Categorize hypotheses
        by_status = {}
        for h in inv.hypotheses:
            if h.status not in by_status:
                by_status[h.status] = []
            by_status[h.status].append(h)
        
        # Get top hypotheses
        top_hypotheses = await self.get_ranked_hypotheses(investigation_id, limit=5)
        
        # Calculate investigation metrics
        total = len(inv.hypotheses)
        tested = len([h for h in inv.hypotheses if h.status in ["supported", "refuted", "inconclusive"]])
        avg_confidence = sum(h.confidence for h in inv.hypotheses) / total if total > 0 else 0
        
        return {
            "investigation": {
                "id": inv.id,
                "name": inv.name,
                "status": inv.status,
                "created_at": inv.created_at.isoformat()
            },
            "metrics": {
                "total_hypotheses": total,
                "tested_hypotheses": tested,
                "pending_hypotheses": len(by_status.get("pending", [])),
                "supported_hypotheses": len(by_status.get("supported", [])),
                "refuted_hypotheses": len(by_status.get("refuted", [])),
                "average_confidence": round(avg_confidence, 3),
                "entity_count": len(inv.entities)
            },
            "top_hypotheses": [
                {
                    "id": h.id,
                    "statement": h.statement,
                    "type": h.hypothesis_type,
                    "status": h.status,
                    "confidence": h.confidence,
                    "relevance": h.relevance,
                    "priority": h.priority,
                    "evidence_count": len(h.evidence)
                }
                for h in top_hypotheses
            ],
            "recommendations": self._generate_recommendations(inv, by_status)
        }
    
    def _generate_recommendations(
        self,
        inv: Investigation,
        by_status: Dict[str, List[Hypothesis]]
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        pending = by_status.get("pending", [])
        if pending:
            top_pending = max(pending, key=lambda h: h.priority)
            recommendations.append(
                f"Test high-priority hypothesis: '{top_pending.statement[:50]}...' "
                f"(priority: {top_pending.priority:.2f})"
            )
        
        # Check for hypotheses needing more evidence
        low_evidence = [h for h in inv.hypotheses if len(h.evidence) < 2 and h.status == "pending"]
        if low_evidence:
            recommendations.append(
                f"Gather more evidence for {len(low_evidence)} hypotheses with insufficient data"
            )
        
        # Check for high-confidence supported hypotheses
        supported = by_status.get("supported", [])
        high_confidence = [h for h in supported if h.confidence > 0.8]
        if high_confidence:
            recommendations.append(
                f"Document {len(high_confidence)} high-confidence findings for final report"
            )
        
        if not recommendations:
            recommendations.append("Continue gathering entities and generating hypotheses")
        
        return recommendations
    
    def get_investigation(self, investigation_id: str) -> Optional[Investigation]:
        """Get an investigation by ID."""
        return self.investigations.get(investigation_id)
    
    def to_dict(self, investigation_id: str) -> Dict[str, Any]:
        """Export investigation to dictionary format."""
        inv = self.investigations.get(investigation_id)
        if not inv:
            return {}
        
        return {
            "id": inv.id,
            "name": inv.name,
            "description": inv.description,
            "status": inv.status,
            "created_at": inv.created_at.isoformat(),
            "entities": inv.entities,
            "hypotheses": [
                {
                    "id": h.id,
                    "statement": h.statement,
                    "type": h.hypothesis_type,
                    "status": h.status,
                    "confidence": h.confidence,
                    "relevance": h.relevance,
                    "priority": h.priority,
                    "test_description": h.test_description,
                    "evidence": h.evidence,
                    "evaluations": h.evaluations,
                    "created_at": h.created_at.isoformat(),
                    "updated_at": h.updated_at.isoformat()
                }
                for h in inv.hypotheses
            ]
        }
