from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class AgentState:
    raw_inputs: List[str]
    parsed_items: List[Dict[str, Any]]
    signals: Dict[str, float]
    insights: List[str]
    confidence_score: float
