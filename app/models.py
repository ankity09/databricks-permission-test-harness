from pydantic import BaseModel, Field
from typing import Literal, Optional


class ActionDescriptor(BaseModel):
    id: str
    tab: str
    label: str
    grant_sql: str
    revoke_sql: str
    probe: dict
    side_effect: str = "none"


class ApplyRequest(BaseModel):
    action_id: str
    securable: str
    level: Optional[str] = None


class ProbeRequest(BaseModel):
    action_id: str
    securable: str
    really_do: bool = False
    negative_test: bool = False


class ProbeResult(BaseModel):
    status: Literal["pass", "fail_denied", "grant_failed", "error"]
    detail: str = ""
    raw_error: str = ""
    rows: Optional[list[dict]] = None


class PromoteInfo(BaseModel):
    grant_sql: str
    uc_deep_link: str


class ScenarioItem(BaseModel):
    action_id: str
    securable: str


class ScenarioRunRequest(BaseModel):
    items: list[ScenarioItem]
    scenario_id: Optional[str] = None


class ScenarioSaveRequest(BaseModel):
    name: str
    description: str = ""
    items: list[ScenarioItem]


class AgentChatRequest(BaseModel):
    messages: list[dict]


class QueryRequest(BaseModel):
    # exactly one of sql (free-text, read-only enforced) or table (guided path)
    sql: Optional[str] = None
    table: Optional[str] = None
    limit: int = 50


class SweepRequest(BaseModel):
    securable: str