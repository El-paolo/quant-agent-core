from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class AgentState:
    #INPUTS
    company: str
    requested_series: List[str]
    
    ################
    #RAW DATA
    ################
    raw_inputs: List[str]
    raw_news: List[dict]
    time_series_data: Dict[str, List[float]] = field(default_factory=dict)
    ################
    #PROCESSED DATA
    ################
    cleaned_series: Dict[str, Any] = field(default_factory=dict)
    relevant_news: List[dict] = field(default_factory=list)
    ################
    #METRICS
    ################
    metrics: Dict[str, Any] = field(default_factory=dict)


    ################
    #NLP
    ################
    report_summary: str | None = None
    sentiment_score: float
    
    