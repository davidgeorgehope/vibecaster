"""Shared pytest fixtures for agent tests."""
import pytest
from unittest.mock import patch


@pytest.fixture
def mock_requests():
    """Mock requests library for URL validation."""
    with patch('agents.requests') as mock_req:
        yield mock_req


@pytest.fixture
def sample_html_content():
    """Sample HTML content for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Test Article About Kubernetes</title></head>
    <body>
        <article>
            <h1>Understanding Kubernetes Pod Scheduling</h1>
            <p>Kubernetes scheduling is a complex topic that involves multiple components...</p>
            <p>The scheduler uses various algorithms to place pods on nodes.</p>
        </article>
    </body>
    </html>
    """


@pytest.fixture
def sample_404_html():
    """Sample 404 HTML content for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Page Not Found</title></head>
    <body>
        <h1>404 - Page Not Found</h1>
        <p>The page you're looking for doesn't exist.</p>
    </body>
    </html>
    """


@pytest.fixture
def sample_soft_404_html():
    """Sample soft 404 HTML content for testing (200 status but 404 content)."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Elastic - We couldn't find that page</title></head>
    <body>
        <div class="error-page">
            <h1>Hmmm… something's amiss</h1>
            <p>We're really good at search but can't seem to find what you're looking for.</p>
        </div>
    </body>
    </html>
    """
