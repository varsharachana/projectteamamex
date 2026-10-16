import random
import re
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import CreditCard, Transaction, User, UserPreference
from app.schemas import (
    BankSelectionInput,
    CardConnectInput,
    CreditCardOut,
    StatementFetchInput,
    StatementOut,
    TokenResponse,
    TransactionCategoryUpdate,
    TransactionOut,
    UserCreate,
    UserLogin,
    UserOut,
    UserProfileOut,
)
from app.security import create_access_token, decode_access_token, hash_password, verify_password

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

BANK_NAMES = {"HDFC", "SBI", "ICICI"}
CATEGORY_ORDER = [
    "Groceries",
    "Dining",
    "Shopping",
    "Transport",
    "Utilities",
    "Travel",
    "Healthcare",
    "Entertainment",
    "Other",
    "Needs Review",
]
BANK_MERCHANTS = {
    "HDFC": [
        "Fresh Basket",
        "Metro Mart",
        "FuelPoint",
        "City Cafe",
        "TravelPlus",
        "Aster Labs",
        "HomeFlow",
        "Skyline Cinema",
    ],
    "SBI": [
        "GreenCart",
        "QuickBites",
        "Metro Rail",
        "EnerGo",
        "Lakshmi Pharmacy",
        "Bharat Bazaar",
        "Namma Cinema",
        "Weekend Mall",
    ],
    "ICICI": [
        "Savory Table",
        "SmartMart",
        "RideNow",
        "Luxe Avenue",
        "City Transit",
        "WellCare",
        "Blue Horizon",
        "Playhouse",
    ],
}
CATEGORY_MERCHANTS = {
    "Groceries": ["Fresh Basket", "GreenCart", "Metro Mart", "Daily Essentials"],
    "Dining": ["City Cafe", "QuickBites", "Savory Table", "Night Noodles"],
    "Shopping": ["Luxe Avenue", "Weekend Mall", "Urban Style", "SmartMart"],
    "Transport": ["Metro Rail", "RideNow", "FuelPoint", "City Transit"],
    "Utilities": ["PowerGrid", "HomeFlow", "EnerGo", "Water Works"],
    "Travel": ["TravelPlus", "Skyline Air", "RailFast", "Hotel Bay"],
    "Healthcare": ["Aster Labs", "WellCare", "Clinic Care", "Care Pharmacy"],
    "Entertainment": ["Skyline Cinema", "Playhouse", "Live Arena", "Cinema Luxe"],
    "Other": ["Global Services", "Office Mart", "QuickPay", "Digital Plus"],
}


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header required")

    token = authorization.split(" ", 1)[1]
    email = decode_access_token(token)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def normalize_bank_name(raw_value: str) -> str:
    value = raw_value.strip().upper()
    if value not in BANK_NAMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported bank selection")
    return value


def mask_card_number(card_number: str) -> str:
    digits = re.sub(r"\D", "", card_number)
    if not digits:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Card number is required")
    if len(digits) < 16 or len(digits) > 19:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Card number must contain 16 to 19 digits")
    return f"•••• •••• •••• {digits[-4:]}"


def luhn_is_valid(card_number: str) -> bool:
    digits = re.sub(r"\D", "", card_number)
    if not digits or len(digits) < 12:
        return False

    total = 0
    reversed_digits = digits[::-1]
    for index, char in enumerate(reversed_digits):
        num = int(char)
        if index % 2 == 1:
            num *= 2
            if num > 9:
                num -= 9
        total += num
    return total % 10 == 0


def build_statement_period(period_label: str, start_date: date, end_date: date) -> str:
    if start_date.month == end_date.month and start_date.year == end_date.year:
        return start_date.strftime("%B %Y")
    return f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}"


def generate_synthetic_transactions(bank_name: str, start_date: date, end_date: date, user_id: int, card_id: int) -> List[Transaction]:
    transactions: List[Transaction] = []
    duration_days = max(1, (end_date - start_date).days)
    for i in range(12):
        offset = random.randint(0, duration_days)
        transaction_day = start_date + timedelta(days=offset)
        category = CATEGORY_ORDER[i % len(CATEGORY_ORDER)] if i % 5 != 0 else "Needs Review"
        if category == "Needs Review":
            category = "Needs Review"
        merchant_source = CATEGORY_MERCHANTS.get(category, BANK_MERCHANTS[bank_name])
        merchant = random.choice(merchant_source)
        amount = round(random.uniform(45.0, 780.0), 2)
        confidence = "High" if category in {"Groceries", "Dining"} else "Medium" if category != "Needs Review" else "Low"
        explanation = (
            "Flagged for manual review because the merchant pattern is ambiguous."
            if category == "Needs Review"
            else "Simulated classification based on merchant pattern and spending history."
        )
        transactions.append(
            Transaction(
                user_id=user_id,
                card_id=card_id,
                bank_name=bank_name,
                merchant=merchant,
                amount=amount,
                category=category,
                confidence=confidence,
                explanation=explanation,
                transaction_date=transaction_day,
            )
        )
    return transactions


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.post("/api/auth/signup", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    existing_user = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An account already exists for this email")

    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        user=UserOut(id=user.id, full_name=user.full_name, email=user.email),
    )


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        user=UserOut(id=user.id, full_name=user.full_name, email=user.email),
    )


@app.get("/api/profile", response_model=UserProfileOut)
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserProfileOut:
    preference = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    cards = db.query(CreditCard).filter(CreditCard.user_id == current_user.id).order_by(CreditCard.created_at.desc()).all()

    return UserProfileOut(
        id=current_user.id,
        name=current_user.full_name,
        email=current_user.email,
        selected_bank=preference.selected_bank if preference else None,
        connected_cards=[
            CreditCardOut(
                id=card.id,
                bank_name=card.bank_name,
                cardholder_name=card.cardholder_name,
                masked_card_number=card.masked_card_number,
                last_four_digits=card.last_four_digits,
                mobile_number=card.mobile_number,
                consent=card.consent,
                created_at=card.created_at,
            )
            for card in cards
        ],
    )


@app.post("/api/profile/bank-selection")
def save_bank_selection(
    payload: BankSelectionInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bank_name = normalize_bank_name(payload.bank_name)
    preference = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if preference:
        preference.selected_bank = bank_name
        preference.updated_at = datetime.utcnow()
    else:
        preference = UserPreference(user_id=current_user.id, selected_bank=bank_name)
        db.add(preference)
    db.commit()
    return {"selected_bank": bank_name}


@app.get("/api/cards", response_model=List[CreditCardOut])
def get_cards(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> List[CreditCardOut]:
    cards = db.query(CreditCard).filter(CreditCard.user_id == current_user.id).order_by(CreditCard.created_at.desc()).all()
    return [
        CreditCardOut(
            id=card.id,
            bank_name=card.bank_name,
            cardholder_name=card.cardholder_name,
            masked_card_number=card.masked_card_number,
            last_four_digits=card.last_four_digits,
            mobile_number=card.mobile_number,
            consent=card.consent,
            created_at=card.created_at,
        )
        for card in cards
    ]


@app.post("/api/cards/connect", status_code=status.HTTP_201_CREATED, response_model=CreditCardOut)
def connect_card(
    payload: CardConnectInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditCardOut:
    if not payload.consent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required to continue")

    bank_name = normalize_bank_name(payload.bank_name)
    if not luhn_is_valid(payload.card_number):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Card number is invalid")

    digits = re.sub(r"\D", "", payload.card_number)
    card = CreditCard(
        user_id=current_user.id,
        bank_name=bank_name,
        cardholder_name=payload.cardholder_name.strip(),
        masked_card_number=mask_card_number(digits),
        last_four_digits=digits[-4:],
        mobile_number=payload.mobile_number.strip(),
        consent=payload.consent,
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    preference = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if preference:
        preference.selected_bank = bank_name
        preference.updated_at = datetime.utcnow()
    else:
        db.add(UserPreference(user_id=current_user.id, selected_bank=bank_name))
    db.commit()

    return CreditCardOut(
        id=card.id,
        bank_name=card.bank_name,
        cardholder_name=card.cardholder_name,
        masked_card_number=card.masked_card_number,
        last_four_digits=card.last_four_digits,
        mobile_number=card.mobile_number,
        consent=card.consent,
        created_at=card.created_at,
    )


@app.post("/api/statements/fetch", response_model=StatementOut)
def fetch_statement(
    payload: StatementFetchInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StatementOut:
    bank_name = normalize_bank_name(payload.bank_name)
    card = (
        db.query(CreditCard)
        .filter(CreditCard.user_id == current_user.id, CreditCard.bank_name == bank_name)
        .order_by(CreditCard.created_at.desc())
        .first()
    )
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No connected card found for this bank")

    if payload.statement_month:
        year_str, month_str = payload.statement_month.split("-", 1)
        year = int(year_str)
        month = int(month_str)
        start_date = date(year, month, 1)
        end_date = date(year + (month // 12), 1 if month < 12 else 1, 1) if False else date(year, month, 28)
        last_day = (date(year + (month // 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1))
        end_date = last_day
        period_label = f"{start_date.strftime('%B %Y')}"
    else:
        if not payload.custom_start_date or not payload.custom_end_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a statement month or a custom date range")
        start_date = date.fromisoformat(payload.custom_start_date)
        end_date = date.fromisoformat(payload.custom_end_date)
        if start_date > end_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start date must be before end date")
        period_label = f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}"

    db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.card_id == card.id,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
    ).delete()

    transactions = generate_synthetic_transactions(bank_name, start_date, end_date, current_user.id, card.id)
    db.add_all(transactions)
    db.commit()

    saved_transactions = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == current_user.id,
            Transaction.card_id == card.id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
        )
        .order_by(Transaction.transaction_date.desc())
        .all()
    )

    return StatementOut(
        bank_name=bank_name,
        card_number=card.masked_card_number,
        period_label=period_label,
        transactions=[
            TransactionOut(
                id=item.id,
                bank_name=item.bank_name,
                merchant=item.merchant,
                amount=float(item.amount),
                category=item.category,
                confidence=item.confidence,
                explanation=item.explanation,
                transaction_date=item.transaction_date,
            )
            for item in saved_transactions
        ],
    )


@app.put("/api/transactions/{transaction_id}/category", response_model=TransactionOut)
def update_transaction_category(
    transaction_id: int,
    payload: TransactionCategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    transaction = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
        .first()
    )
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    normalized_category = payload.category.strip()
    if normalized_category not in CATEGORY_ORDER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")

    transaction.category = normalized_category
    transaction.confidence = payload.confidence or ("High" if normalized_category in {"Groceries", "Dining"} else "Medium")
    transaction.explanation = payload.explanation or "User-corrected category based on manual review."
    db.commit()
    db.refresh(transaction)

    return TransactionOut(
        id=transaction.id,
        bank_name=transaction.bank_name,
        merchant=transaction.merchant,
        amount=float(transaction.amount),
        category=transaction.category,
        confidence=transaction.confidence,
        explanation=transaction.explanation,
        transaction_date=transaction.transaction_date,
    )


@app.get("/api/profile/summary")
def get_profile_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    cards = db.query(CreditCard).filter(CreditCard.user_id == current_user.id).all()
    preference = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    return {
        "user": {"id": current_user.id, "name": current_user.full_name, "email": current_user.email},
        "selected_bank": preference.selected_bank if preference else None,
        "card_count": len(cards),
    }
