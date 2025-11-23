import pytest
from fastapi.testclient import TestClient
import os
import sqlite3
from main import app
from database import init_database, DB_PATH

# Create a test client
client = TestClient(app)

# Test database path
TEST_DB_PATH = "test_vibecaster.db"


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Set up a test database before each test and clean up after."""
    # Use a test database
    monkeypatch.setattr("database.DB_PATH", TEST_DB_PATH)

    # Remove test database if it exists
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    # Initialize test database
    init_database()

    yield

    # Clean up test database
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


class TestSignup:
    """Test user signup functionality."""

    def test_signup_success(self):
        """Test successful user signup."""
        response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0

    def test_signup_short_password(self):
        """Test signup with password too short."""
        response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "short"}
        )

        assert response.status_code == 400
        assert "at least 8 characters" in response.json()["detail"]

    def test_signup_duplicate_email(self):
        """Test signup with duplicate email."""
        # Create first user
        client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )

        # Try to create duplicate
        response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password456"}
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    def test_signup_invalid_email(self):
        """Test signup with invalid email."""
        response = client.post(
            "/api/auth/signup",
            json={"email": "not-an-email", "password": "password123"}
        )

        assert response.status_code == 422  # Validation error


class TestLogin:
    """Test user login functionality."""

    def test_login_success(self):
        """Test successful login."""
        # Create a user first
        client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )

        # Login
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "password123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self):
        """Test login with wrong password."""
        # Create a user first
        client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )

        # Try to login with wrong password
        response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"}
        )

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self):
        """Test login with non-existent user."""
        response = client.post(
            "/api/auth/login",
            json={"email": "nonexistent@example.com", "password": "password123"}
        )

        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]


class TestAuthenticatedEndpoints:
    """Test endpoints that require authentication."""

    def test_get_current_user_success(self):
        """Test getting current user with valid token."""
        # Signup
        signup_response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )
        token = signup_response.json()["access_token"]

        # Get current user
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert "id" in data
        assert "created_at" in data

    def test_get_current_user_no_token(self):
        """Test getting current user without token."""
        response = client.get("/api/auth/me")

        assert response.status_code == 403  # Forbidden (no credentials)

    def test_get_current_user_invalid_token(self):
        """Test getting current user with invalid token."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401

    def test_get_current_user_malformed_token(self):
        """Test getting current user with malformed token."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer"}
        )

        assert response.status_code == 403  # No credentials


class TestSignupLoginFlow:
    """Test the complete signup-login flow."""

    def test_signup_then_fetch_user(self):
        """Test signup followed by fetching user data - this is the bug scenario."""
        # Signup
        signup_response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )

        assert signup_response.status_code == 201
        token = signup_response.json()["access_token"]

        # Immediately fetch user data (this was failing before the fix)
        user_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert user_response.status_code == 200
        user_data = user_response.json()
        assert user_data["email"] == "test@example.com"
        assert isinstance(user_data["id"], int)
        assert isinstance(user_data["created_at"], int)

    def test_signup_then_login_then_fetch_user(self):
        """Test full flow: signup -> login -> fetch user."""
        # Signup
        signup_response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )
        assert signup_response.status_code == 201

        # Login
        login_response = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "password123"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Fetch user
        user_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert user_response.status_code == 200
        assert user_response.json()["email"] == "test@example.com"

    def test_token_persistence(self):
        """Test that token works across multiple requests."""
        # Signup
        signup_response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123"}
        )
        token = signup_response.json()["access_token"]

        # Make multiple requests with the same token
        for _ in range(3):
            response = client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            assert response.json()["email"] == "test@example.com"
