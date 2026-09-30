"""
Opportunity Monitor
Tracks and monitors opportunities like grants, accelerators, competitions, etc.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class OpportunityType(Enum):
    """Types of opportunities."""
    GRANT = "grant"
    ACCELERATOR = "accelerator"
    COMPETITION = "competition"
    PARTNERSHIP = "partnership"
    SPEAKING = "speaking"
    MEDIA = "media"
    FUNDING = "funding"
    OTHER = "other"


class OpportunityStatus(Enum):
    """Status of an opportunity."""
    DISCOVERED = "discovered"
    REVIEWING = "reviewing"
    INTERESTED = "interested"
    APPLYING = "applying"
    SUBMITTED = "submitted"
    AWAITING_RESPONSE = "awaiting_response"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NOT_PURSUING = "not_pursuing"


@dataclass
class Opportunity:
    """An opportunity for Sabi."""
    id: str
    title: str
    type: OpportunityType
    description: str
    status: OpportunityStatus
    source: str
    url: Optional[str]
    deadline: Optional[str]
    amount: Optional[str]
    requirements: List[str]
    fit_score: Optional[float]  # 0-1 score of how well it fits Sabi
    notes: str
    created_at: str
    updated_at: str
    metadata: Dict
    
    def __post_init__(self):
        if self.requirements is None:
            self.requirements = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['type'] = self.type.value
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Opportunity':
        data['type'] = OpportunityType(data['type'])
        data['status'] = OpportunityStatus(data['status'])
        return cls(**data)


class OpportunityMonitor:
    """
    Monitors and tracks opportunities for Sabi.
    Helps identify grants, partnerships, and other growth opportunities.
    """
    
    def __init__(self, data_dir: str = "cofounder_agent/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.opportunities_file = self.data_dir / "opportunities.json"
        self.search_config_file = self.data_dir / "opportunity_search_config.json"
        
        self.opportunities: Dict[str, Opportunity] = {}
        self.search_config: Dict = self._default_search_config()
        
        self._load()
    
    def _default_search_config(self) -> Dict:
        """Default search configuration for opportunities."""
        return {
            "keywords": [
                "education grant Africa",
                "edtech accelerator",
                "Nigeria education funding",
                "AI education grant",
                "social impact grant Africa",
                "education technology competition"
            ],
            "focus_areas": [
                "education technology",
                "AI/ML in education",
                "African edtech",
                "social impact",
                "early childhood education"
            ],
            "excluded_terms": [
                "US only",
                "Europe only"
            ],
            "check_frequency_days": 7
        }
    
    def _load(self):
        """Load opportunities and config from disk."""
        if self.opportunities_file.exists():
            with open(self.opportunities_file, 'r') as f:
                data = json.load(f)
                self.opportunities = {
                    opp_id: Opportunity.from_dict(opp_data)
                    for opp_id, opp_data in data.items()
                }
        
        if self.search_config_file.exists():
            with open(self.search_config_file, 'r') as f:
                self.search_config = json.load(f)
    
    def _save(self):
        """Save opportunities and config to disk."""
        with open(self.opportunities_file, 'w') as f:
            data = {opp_id: opp.to_dict() for opp_id, opp in self.opportunities.items()}
            json.dump(data, f, indent=2)
        
        with open(self.search_config_file, 'w') as f:
            json.dump(self.search_config, f, indent=2)
    
    def add_opportunity(
        self,
        title: str,
        opp_type: OpportunityType,
        description: str,
        source: str,
        url: Optional[str] = None,
        deadline: Optional[str] = None,
        amount: Optional[str] = None,
        requirements: Optional[List[str]] = None,
        fit_score: Optional[float] = None,
        notes: str = "",
        metadata: Optional[Dict] = None
    ) -> str:
        """Add a new opportunity."""
        opp_id = f"opp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        now = datetime.now().isoformat()
        
        opportunity = Opportunity(
            id=opp_id,
            title=title,
            type=opp_type,
            description=description,
            status=OpportunityStatus.DISCOVERED,
            source=source,
            url=url,
            deadline=deadline,
            amount=amount,
            requirements=requirements or [],
            fit_score=fit_score,
            notes=notes,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        self.opportunities[opp_id] = opportunity
        self._save()
        return opp_id
    
    def update_opportunity(
        self,
        opp_id: str,
        status: Optional[OpportunityStatus] = None,
        notes: Optional[str] = None,
        fit_score: Optional[float] = None,
        metadata: Optional[Dict] = None
    ):
        """Update an opportunity."""
        if opp_id not in self.opportunities:
            raise ValueError(f"Opportunity {opp_id} not found")
        
        opp = self.opportunities[opp_id]
        
        if status is not None:
            opp.status = status
        if notes is not None:
            opp.notes = notes
        if fit_score is not None:
            opp.fit_score = fit_score
        if metadata is not None:
            opp.metadata.update(metadata)
        
        opp.updated_at = datetime.now().isoformat()
        self._save()
    
    def get_opportunity(self, opp_id: str) -> Optional[Opportunity]:
        """Get a specific opportunity."""
        return self.opportunities.get(opp_id)
    
    def get_active_opportunities(self) -> List[Opportunity]:
        """Get all opportunities that are still active."""
        active_statuses = [
            OpportunityStatus.DISCOVERED,
            OpportunityStatus.REVIEWING,
            OpportunityStatus.INTERESTED,
            OpportunityStatus.APPLYING,
            OpportunityStatus.SUBMITTED,
            OpportunityStatus.AWAITING_RESPONSE
        ]
        return [
            opp for opp in self.opportunities.values()
            if opp.status in active_statuses
        ]
    
    def get_high_fit_opportunities(self, min_score: float = 0.7) -> List[Opportunity]:
        """Get opportunities with high fit scores."""
        return [
            opp for opp in self.get_active_opportunities()
            if opp.fit_score and opp.fit_score >= min_score
        ]
    
    def get_upcoming_deadlines(self, days: int = 30) -> List[Opportunity]:
        """Get opportunities with deadlines in the next N days."""
        from datetime import timedelta
        cutoff = datetime.now() + timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        return [
            opp for opp in self.get_active_opportunities()
            if opp.deadline and opp.deadline <= cutoff_str
        ]
    
    def update_search_config(self, config: Dict):
        """Update the search configuration."""
        self.search_config.update(config)
        self._save()
    
    def get_dashboard_summary(self) -> Dict:
        """Get a summary of opportunities."""
        active = self.get_active_opportunities()
        high_fit = self.get_high_fit_opportunities()
        upcoming = self.get_upcoming_deadlines()
        
        return {
            "total_opportunities": len(self.opportunities),
            "active_opportunities": len(active),
            "high_fit_count": len(high_fit),
            "upcoming_deadlines": len(upcoming),
            "by_type": {
                opp_type.value: len([
                    o for o in active if o.type == opp_type
                ])
                for opp_type in OpportunityType
            },
            "by_status": {
                status.value: len([
                    o for o in self.opportunities.values() if o.status == status
                ])
                for status in OpportunityStatus
            }
        }
    
    def calculate_fit_score(
        self,
        opp_description: str,
        opp_requirements: List[str],
        sabi_profile: Dict
    ) -> float:
        """
        Calculate how well an opportunity fits Sabi.
        This is a simple keyword-based scorer. In production, you'd use LLM analysis.
        """
        score = 0.5  # baseline
        
        focus_areas = sabi_profile.get("focus_areas", [])
        strengths = sabi_profile.get("strengths", [])
        
        description_lower = opp_description.lower()
        
        for area in focus_areas:
            if area.lower() in description_lower:
                score += 0.1
        
        for strength in strengths:
            if strength.lower() in description_lower:
                score += 0.1
        
        return min(score, 1.0)
