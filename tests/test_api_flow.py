import os

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    db_path = os.path.join(os.path.dirname(__file__), "..", "credit_card_agent.db")
    db_path = os.path.abspath(db_path)
    if os.path.exists(db_path):
        os.remove(db_path)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_signup_login_profile_and_category_flow():
    signup = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Aarav Mehta",
            "email": "aarav@example.com",
            "password": "StrongPass123!",
        },
    )
    assert signup.status_code == 201, signup.text
    token = signup.json()["access_token"]
    assert token

    profile = client.get(
        "/api/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["name"] == "Aarav Mehta"

    connect = client.post(
        "/api/cards/connect",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bank_name": "HDFC",
            "cardholder_name": "Aarav Mehta",
            "card_number": "4556 7821 0945 3312",
            "mobile_number": "+91 98765 43210",
            "consent": True,
        },
    )
    assert connect.status_code == 201, connect.text
    data = connect.json()
    assert data["last_four_digits"] == "3312"
    assert "4556" not in data["masked_card_number"]

    statement = client.post(
        "/api/statements/fetch",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bank_name": "HDFC",
            "statement_month": "2026-10",
        },
    )
    assert statement.status_code == 200, statement.text
    payload = statement.json()
    assert payload["transactions"]
    tx = payload["transactions"][0]
    assert "category" in tx

    update = client.put(
        f"/api/transactions/{tx['id']}/category",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "category": "Dining",
            "confidence": "High",
            "explanation": "Updated by user review",
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["category"] == "Dining"


def test_signup_validation_requires_unique_email():
    first = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Test User",
            "email": "test.validation@example.com",
            "password": "StrongPass123!",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Second User",
            "email": "test.validation@example.com",
            "password": "StrongPass123!",
        },
    )
    assert second.status_code == 400
