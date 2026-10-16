import re
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


def validate_password_strength(password: str) -> str:
    if len(password) < 15:
        raise ValueError("Password must be at least 15 characters long.")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain letters.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain numbers.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character.")
    return password


class UserCreate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=15, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def normalize_name(cls, data):
        if isinstance(data, dict):
            if data.get("name") and not data.get("full_name"):
                data["full_name"] = data["name"]
            elif data.get("full_name") and not data.get("name"):
                data["name"] = data["full_name"]
            if not data.get("name") and not data.get("full_name"):
                raise ValueError("name or full_name is required")
        return data

    @property
    def resolved_name(self) -> str:
        return (self.name or self.full_name or "").strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=15, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    full_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BankSelectionInput(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=50)

    model_config = ConfigDict(extra="forbid")


class CardConnectInput(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=50)
    cardholder_name: str = Field(..., min_length=2, max_length=120)
    card_number: str = Field(..., min_length=12, max_length=24)
    mobile_number: str = Field(..., min_length=8, max_length=30)
    consent: bool = True

    model_config = ConfigDict(extra="forbid")


class CreditCardOut(BaseModel):
    id: int
    bank_name: str
    cardholder_name: str
    masked_card_number: str
    last_four_digits: str
    mobile_number: str
    consent: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionCategoryUpdate(BaseModel):
    category: str = Field(..., min_length=2, max_length=50)
    confidence: str = Field(default="Medium", min_length=2, max_length=20)
    explanation: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class TransactionOut(BaseModel):
    id: int
    bank_name: str
    merchant: str
    amount: float
    category: str
    confidence: str
    explanation: str
    transaction_date: date

    model_config = ConfigDict(from_attributes=True)


class StatementFetchInput(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=50)
    statement_month: Optional[str] = None
    custom_start_date: Optional[str] = None
    custom_end_date: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class StatementOut(BaseModel):
    bank_name: str
    card_number: str
    period_label: str
    transactions: List[TransactionOut]


class RewardRedemptionInput(BaseModel):
    points: int = Field(..., gt=0, le=100000)
    bank_name: str = Field(..., min_length=2, max_length=50)

    model_config = ConfigDict(extra="forbid")


class RewardMetric(BaseModel):
    month: str
    points: int


class RewardTransaction(BaseModel):
    merchant: str
    amount: float
    points: int
    category: str
    bank_name: str


class RewardsSummaryOut(BaseModel):
    user_id: int
    integration_available: bool
    available_points: int
    monthly_earnings: List[RewardMetric]
    expiring_points: int
    bank_filter_options: List[str]
    points_by_bank: dict
    redemption_enabled: bool
    redemption_history: List[dict]
    transaction_rewards: List[RewardTransaction]


class RewardRedemptionResult(BaseModel):
    success: bool
    message: str
    bank_name: str
    points_redeemed: int
    remaining_points: int


class UserProfileOut(BaseModel):
    id: int
    name: str
    email: str
    selected_bank: Optional[str]
    connected_cards: List[CreditCardOut]

    model_config = ConfigDict(from_attributes=True)
