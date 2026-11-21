"""EXAMFLOW – pytest configuration and fixtures"""
import pytest
import asyncio
from typing import AsyncGenerator

# Async test support
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
