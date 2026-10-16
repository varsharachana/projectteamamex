import random
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import CreditCard, Transaction, User, UserPreference
from app.schemas import (
    BankSelectionInput,
    CardConnectInput,
    CreditCardOut,
    RewardRedemptionInput,
    RewardRedemptionResult,
    RewardsSummaryOut,
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


def resolve_database_path() -> str:
    database_url = settings.database_url
    if not database_url.startswith("sqlite"):
        return database_url

    raw_path = database_url.replace("sqlite:///", "", 1)
    if not raw_path:
        return str(Path("app.db").resolve())

    candidate = Path(raw_path)
    if candidate.is_absolute():
        return str(candidate.resolve())
    return str((Path.cwd() / candidate).resolve())


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)
    print(f"SQLite database path: {resolve_database_path()}")


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


def get_owned_card_or_404(db: Session, user_id: int, card_id: int) -> CreditCard:
    card = db.query(CreditCard).filter(CreditCard.id == card_id, CreditCard.user_id == user_id).first()
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found or not owned by this user")
    return card


def get_owned_transaction_or_404(db: Session, user_id: int, transaction_id: int) -> Transaction:
    transaction = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == user_id)
        .first()
    )
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found or not owned by this user")
    return transaction


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


def calculate_reward_points(amount: float, bank_name: str) -> int:
    base_points = max(0, int(round(float(amount) / 10)))
    bank_multiplier = {"HDFC": 1.0, "SBI": 1.15, "ICICI": 1.1}.get(bank_name, 1.0)
    return max(0, int(base_points * bank_multiplier))


def build_user_rewards_payload(current_user: User, db: Session) -> dict:
    cards = db.query(CreditCard).filter(CreditCard.user_id == current_user.id).all()
    bank_names = sorted({card.bank_name for card in cards})
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .order_by(Transaction.transaction_date.desc())
        .all()
    )
    bank_points = defaultdict(int)
    monthly_points = defaultdict(int)
    transaction_rewards = []
    redemption_history = []

    for item in transactions:
        points = calculate_reward_points(float(item.amount), item.bank_name)
        bank_points[item.bank_name] += points
        month_key = item.transaction_date.strftime("%Y-%m")
        monthly_points[month_key] += points
        transaction_rewards.append(
            {
                "merchant": item.merchant,
                "amount": float(item.amount),
                "points": points,
                "category": item.category,
                "bank_name": item.bank_name,
            }
        )

    monthly_earnings = [
        {"month": month, "points": total}
        for month, total in sorted(monthly_points.items())[-6:]
    ]
    available_points = sum(bank_points.values())

    return {
        "user_id": current_user.id,
        "integration_available": bool(settings.rewards_integration_enabled),
        "available_points": available_points,
        "monthly_earnings": monthly_earnings,
        "expiring_points": max(0, available_points // 3),
        "bank_filter_options": bank_names,
        "points_by_bank": {bank: bank_points.get(bank, 0) for bank in bank_names},
        "redemption_enabled": bool(settings.rewards_integration_enabled) and available_points > 0,
        "redemption_history": redemption_history,
        "transaction_rewards": transaction_rewards[:10],
    }


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
    email = payload.email.lower().strip()
    normalized_name = (payload.resolved_name or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required")

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account already exists. Please log in.")

    user = User(
        name=normalized_name,
        email=email,
        password_hash=hash_password(payload.password),
        last_login=datetime.utcnow(),
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account already exists. Please log in.") from None

    token = create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        user=UserOut(id=user.id, name=user.name, email=user.email, full_name=user.name),
    )


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not available. Please sign up.")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password. Please try again.")

    user.last_login = datetime.utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to update login session") from None

    token = create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        user=UserOut(id=user.id, name=user.name, email=user.email, full_name=user.name),
    )


@app.get("/api/profile", response_model=UserProfileOut)
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserProfileOut:
    preference = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    cards = db.query(CreditCard).filter(CreditCard.user_id == current_user.id).order_by(CreditCard.created_at.desc()).all()

    return UserProfileOut(
        id=current_user.id,
        name=current_user.name,
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
    try:
        preference = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
        if preference:
            preference.selected_bank = bank_name
            preference.updated_at = datetime.utcnow()
        else:
            preference = UserPreference(user_id=current_user.id, selected_bank=bank_name)
            db.add(preference)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to save bank selection") from None
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


@app.get("/api/cards/{card_id}", response_model=CreditCardOut)
def get_card_by_id(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditCardOut:
    card = get_owned_card_or_404(db, current_user.id, card_id)
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


@app.get("/api/cards/{card_id}/transactions", response_model=List[TransactionOut])
def get_card_transactions(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[TransactionOut]:
    get_owned_card_or_404(db, current_user.id, card_id)
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id, Transaction.card_id == card_id)
        .order_by(Transaction.transaction_date.desc())
        .all()
    )
    return [
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
        for item in transactions
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
    try:
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
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to save card connection") from None

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

    try:
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
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to save statement data") from None

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


@app.get("/api/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction_by_id(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    transaction = get_owned_transaction_or_404(db, current_user.id, transaction_id)
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


@app.put("/api/transactions/{transaction_id}/category", response_model=TransactionOut)
def update_transaction_category(
    transaction_id: int,
    payload: TransactionCategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    transaction = get_owned_transaction_or_404(db, current_user.id, transaction_id)

    normalized_category = payload.category.strip()
    if normalized_category not in CATEGORY_ORDER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")

    try:
        transaction.category = normalized_category
        transaction.confidence = payload.confidence or ("High" if normalized_category in {"Groceries", "Dining"} else "Medium")
        transaction.explanation = payload.explanation or "User-corrected category based on manual review."
        db.commit()
        db.refresh(transaction)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to update category") from None

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


@app.get("/api/rewards", response_model=RewardsSummaryOut)
def get_rewards_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RewardsSummaryOut:
    payload = build_user_rewards_payload(current_user, db)
    payload["integration_available"] = bool(settings.rewards_integration_enabled)
    payload["redemption_enabled"] = bool(settings.rewards_integration_enabled) and payload["available_points"] > 0
    return RewardsSummaryOut(**payload)


@app.post("/api/rewards/redeem", response_model=RewardRedemptionResult)
def redeem_rewards(
    payload: RewardRedemptionInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RewardRedemptionResult:
    if not settings.rewards_integration_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Rewards data unavailable.")

    rewards = build_user_rewards_payload(current_user, db)
    bank_names = rewards["bank_filter_options"]
    if payload.bank_name not in bank_names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported bank selection")
    if payload.points <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Points must be greater than zero")
    if payload.points > rewards["available_points"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough reward points")

    remaining_points = rewards["available_points"] - payload.points
    return RewardRedemptionResult(
        success=True,
        message="Redemption confirmed.",
        bank_name=payload.bank_name,
        points_redeemed=payload.points,
        remaining_points=remaining_points,
    )


@app.get("/api/profile/summary")
def get_profile_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    cards = db.query(CreditCard).filter(CreditCard.user_id == current_user.id).all()
    preference = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    return {
        "user": {"id": current_user.id, "name": current_user.name, "email": current_user.email},
        "selected_bank": preference.selected_bank if preference else None,
        "card_count": len(cards),
    }
