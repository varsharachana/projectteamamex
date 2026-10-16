from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BankSelectionInput(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=50)


class CardConnectInput(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=50)
    cardholder_name: str = Field(..., min_length=2, max_length=120)
    card_number: str = Field(..., min_length=12, max_length=24)
    mobile_number: str = Field(..., min_length=8, max_length=30)
    consent: bool = True


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


class StatementOut(BaseModel):
    bank_name: str
    card_number: str
    period_label: str
    transactions: List[TransactionOut]


class UserProfileOut(BaseModel):
    id: int
    name: str
    email: str
    selected_bank: Optional[str]
    connected_cards: List[CreditCardOut]

    model_config = ConfigDict(from_attributes=True)
