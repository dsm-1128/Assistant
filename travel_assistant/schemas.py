from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TravelRequest(BaseModel):
    origin: str = Field(min_length=1, description="出发地")
    destination: str = Field(min_length=1, description="目的地")
    start_date: date
    end_date: date
    adults: int = Field(default=1, ge=0)
    children: int = Field(default=0, ge=0)
    budget: float = Field(default=0, ge=0)
    currency: str = Field(default="CNY", min_length=1)
    interests: list[str] = Field(default_factory=list)
    pace: Literal["轻松", "适中", "紧凑"] = "适中"
    accommodation: str = "无特殊要求"
    dietary_restrictions: str = "无"
    must_visit: list[str] = Field(default_factory=list)
    additional_requirements: str = ""

    @model_validator(mode="after")
    def validate_trip(self) -> "TravelRequest":
        if self.start_date > self.end_date:
            raise ValueError("出发日期不能晚于返回日期")
        if self.adults + self.children <= 0:
            raise ValueError("旅行人数必须大于 0")
        return self

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


class Evidence(BaseModel):
    id: str
    content: str
    source: str
    destination: str
    topic: str = "综合"
    updated_at: str = "未知"
    distance: float | None = None


class TimeSlot(BaseModel):
    period: Literal["上午", "下午", "晚上"]
    activity: str
    location: str = ""
    duration: str = ""
    transport: str = ""
    estimated_cost: float = Field(default=0, ge=0)
    citations: list[str] = Field(default_factory=list)


class DayPlan(BaseModel):
    day: int = Field(ge=1)
    date: date
    theme: str
    activities: list[TimeSlot]
    meals: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BudgetItem(BaseModel):
    category: str
    amount: float = Field(ge=0)
    note: str = ""


class TravelGuide(BaseModel):
    title: str
    overview: str
    planning_rationale: list[str]
    days: list[DayPlan]
    transportation_advice: list[str] = Field(default_factory=list)
    food_and_stay_advice: list[str] = Field(default_factory=list)
    budget_items: list[BudgetItem] = Field(default_factory=list)
    budget_total: float = Field(ge=0)
    preparation: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False

    @model_validator(mode="after")
    def validate_budget_total(self) -> "TravelGuide":
        calculated = sum(item.amount for item in self.budget_items)
        if abs(calculated - self.budget_total) > 0.01:
            raise ValueError(
                f"budget_total ({self.budget_total}) 与预算项目合计 ({calculated}) 不一致"
            )
        return self
