"""Endpoint-independent pytest adapter; select this file explicitly for live runs."""
from api_test_tool.pytest_plugin import assert_generated_case


def test_generated_api(generated_case, generated_run):
    assert_generated_case(generated_case, generated_run)
