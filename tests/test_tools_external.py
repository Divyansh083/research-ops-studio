from unittest.mock import MagicMock, patch

import pytest

from app.tools.search_tool import duckduckgo_search
from app.tools.retrieval_tool import retrieve_documents


@patch("app.tools.search_tool.SEARCH_CLIENT")
def test_duckduckgo_search_returns_results(mock_search_client):
    mock_search_client.return_value.__enter__.return_value.text.return_value = [
        {"title": "Test Title", "body": "Test body", "href": "http://test.com"}
    ]

    results = duckduckgo_search("test query")
    assert len(results) == 1
    assert results[0]["title"] == "Test Title"
    assert results[0]["url"] == "http://test.com"


@patch("app.tools.search_tool.SEARCH_CLIENT")
def test_duckduckgo_search_handles_error(mock_search_client):
    mock_search_client.return_value.__enter__.side_effect = Exception("Network error")

    results = duckduckgo_search("test query")
    assert len(results) == 1
    assert "error" in results[0]["title"].lower()


@patch("app.tools.retrieval_tool.get_vectorstore")
def test_retrieve_documents_handles_error(mock_get_vectorstore):
    mock_get_vectorstore.side_effect = Exception("Vector store unavailable")

    results = retrieve_documents("test query")
    assert len(results) == 1
    assert results[0]["source"] == "error"
