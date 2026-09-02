from dataclasses import dataclass


@dataclass(frozen=True)
class IssueRecommendation:
    issue_category: str
    issue_subtype: str
    analysis_reason: str
    recommended_action: str
    recommended_route: str | None
    analysis_mode: str = "EIGHT_AGENT_RULE_ASSISTED"
