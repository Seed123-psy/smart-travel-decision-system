from datetime import date, datetime, time
from decimal import Decimal
from math import ceil
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

SHANGHAI = ZoneInfo("Asia/Shanghai")
Money = Annotated[Decimal, Field(gt=0, le=Decimal("99999999.99"), decimal_places=2)]
City = Annotated[str, Field(min_length=1, max_length=80)]


class DailyWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: time = time(9)
    end: time = time(18)

    @model_validator(mode="after")
    def valid_window(self) -> "DailyWindow":
        if self.start.tzinfo or self.end.tzinfo:
            raise ValueError("每日活动时间使用目的地当地时间，不附带时区偏移")
        if self.start >= self.end:
            raise ValueError("每日活动结束时间必须晚于开始时间")
        return self


class TravelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origin: City
    destination: City
    start_date: date
    end_date: date
    travelers: Annotated[int, Field(ge=1, le=10, strict=True)]
    budget_total: Money
    currency: Literal["CNY"] = "CNY"
    budget_scope: Literal["destination_only"] = "destination_only"
    styles: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(
        default_factory=list, max_length=10
    )
    hotel_preference: Annotated[str, Field(min_length=1, max_length=40)] = "不限"
    pace: Literal["紧凑", "均衡", "休闲"] = "均衡"
    daily_window: DailyWindow = Field(default_factory=DailyWindow)
    rooms: Annotated[int, Field(ge=0, le=10, strict=True)] | None = None
    defaults_confirmed: Literal[True]

    @field_validator("budget_total")
    @classmethod
    def normalize_money(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def validate_trip(self, info: ValidationInfo) -> "TravelRequest":
        today = (info.context or {}).get("today", datetime.now(SHANGHAI).date())
        if self.start_date < today:
            raise ValueError("开始日期不能早于今天（Asia/Shanghai）")
        days = (self.end_date - self.start_date).days + 1
        if not 1 <= days <= 7:
            raise ValueError("起止日期须按顺序填写，行程应为含首尾的 1–7 天")
        if self.rooms is None:
            self.rooms = 0 if days == 1 else ceil(self.travelers / 2)
        if self.rooms > self.travelers:
            raise ValueError("房间数不能超过同行人数")
        if days == 1 and self.rooms != 0:
            raise ValueError("单日行程住宿晚数为 0，房间数应为 0")
        return self


class RequirementValidation(BaseModel):
    valid: Literal[True] = True
    request: TravelRequest
    warnings: list[str]
