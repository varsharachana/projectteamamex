import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.gettempdir(), f'credit_card_agent_test_{uuid.uuid4().hex}.db')}"

from app.database import Base, engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_signup_login_profile_and_category_flow():
    signup = client.post(
        "/api/auth/signup",
        json={
            "name": "Aarav Mehta",
            "email": "aarav@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert signup.status_code == 201, signup.text
    assert signup.json()["user"]["name"] == "Aarav Mehta"
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
            "card_number": "4111 1111 1111 1111",
            "mobile_number": "+91 98765 43210",
            "consent": True,
        },
    )
    assert connect.status_code == 201, connect.text
    data = connect.json()
    assert data["last_four_digits"] == "1111"
    assert "4111" not in data["masked_card_number"]

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


def test_duplicate_signup_and_invalid_login_messages():
    first = client.post(
        "/api/auth/signup",
        json={
            "name": "Test User",
            "email": "duplicate@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/auth/signup",
        json={
            "name": "Another User",
            "email": "duplicate@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert second.status_code == 400, second.text
    assert second.json()["detail"] == "Account already exists. Please log in."

    unknown = client.post(
        "/api/auth/login",
        json={
            "email": "missing@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert unknown.status_code == 401, unknown.text
    assert unknown.json()["detail"] == "Account not available. Please sign up."

    wrong = client.post(
        "/api/auth/login",
        json={
            "email": "duplicate@example.com",
            "password": "WrongPass!2026Now",
        },
    )
    assert wrong.status_code == 401, wrong.text
    assert wrong.json()["detail"] == "Incorrect password. Please try again."


def test_user_isolation_blocks_cross_account_access():
    x = client.post(
        "/api/auth/signup",
        json={
            "full_name": "User X",
            "email": "userx@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert x.status_code == 201, x.text
    x_token = x.json()["access_token"]

    x_card = client.post(
        "/api/cards/connect",
        headers={"Authorization": f"Bearer {x_token}"},
        json={
            "bank_name": "HDFC",
            "cardholder_name": "User X",
            "card_number": "4111 1111 1111 1111",
            "mobile_number": "+91 90000 00001",
            "consent": True,
        },
    )
    assert x_card.status_code == 201, x_card.text
    x_card_id = x_card.json()["id"]

    x_statement = client.post(
        "/api/statements/fetch",
        headers={"Authorization": f"Bearer {x_token}"},
        json={
            "bank_name": "HDFC",
            "statement_month": "2026-10",
        },
    )
    assert x_statement.status_code == 200, x_statement.text
    x_tx_id = x_statement.json()["transactions"][0]["id"]

    y = client.post(
        "/api/auth/signup",
        json={
            "full_name": "User Y",
            "email": "usery@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert y.status_code == 201, y.text
    y_token = y.json()["access_token"]

    card_request = client.get(f"/api/cards/{x_card_id}", headers={"Authorization": f"Bearer {y_token}"})
    assert card_request.status_code == 404, card_request.text

    tx_request = client.get(f"/api/transactions/{x_tx_id}", headers={"Authorization": f"Bearer {y_token}"})
    assert tx_request.status_code == 404, tx_request.text

    tampered_update = client.put(
        f"/api/transactions/{x_tx_id}/category",
        headers={"Authorization": f"Bearer {y_token}"},
        json={
            "category": "Dining",
            "confidence": "High",
            "explanation": "Attempted cross-account modification",
            "user_id": 999,
        },
    )
    assert tampered_update.status_code == 422, tampered_update.text


def test_signup_validation_requires_unique_email():
    first = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Test User",
            "email": "test.validation@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Second User",
            "email": "test.validation@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert second.status_code == 400


def test_password_must_include_letters_numbers_special_characters_and_be_at_least_15_chars():
    weak = client.post(
        "/api/auth/signup",
        json={
            "name": "Weak User",
            "email": "weak@example.com",
            "password": "short",
        },
    )
    assert weak.status_code == 422, weak.text

    strong = client.post(
        "/api/auth/signup",
        json={
            "name": "Strong User",
            "email": "strong@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert strong.status_code == 201, strong.text


def test_rewards_summary_and_redemption_are_user_scoped_and_confirmed():
    os.environ["REWARDS_INTEGRATION_ENABLED"] = "true"
    from importlib import reload
    import app.config as app_config
    reload(app_config)
    from app import main as main_module
    reload(main_module)

    signup = client.post(
        "/api/auth/signup",
        json={
            "name": "Rewards User",
            "email": "rewards@example.com",
            "password": "StrongPass!2026Now",
        },
    )
    assert signup.status_code == 201, signup.text
    token = signup.json()["access_token"]

    connect = client.post(
        "/api/cards/connect",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bank_name": "HDFC",
            "cardholder_name": "Rewards User",
            "card_number": "4111 1111 1111 1111",
            "mobile_number": "+91 98765 43210",
            "consent": True,
        },
    )
    assert connect.status_code == 201, connect.text

    statement = client.post(
        "/api/statements/fetch",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bank_name": "HDFC",
            "statement_month": "2026-10",
        },
    )
    assert statement.status_code == 200, statement.text

    summary = client.get(
        "/api/rewards",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["integration_available"] is True
    assert payload["available_points"] >= 0
    assert payload["user_id"] == signup.json()["user"]["id"]
    assert payload["bank_filter_options"]

    redemption = client.post(
        "/api/rewards/redeem",
        headers={"Authorization": f"Bearer {token}"},
        json={"points": 50, "bank_name": "HDFC"},
    )
    assert redemption.status_code == 200, redemption.text
    assert redemption.json()["success"] is True
    assert redemption.json()["message"] == "Redemption confirmed."
