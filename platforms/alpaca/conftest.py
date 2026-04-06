"""Conftest for Alpaca adapter tests.

Ensures the installed alpaca-py package is importable — the platforms/alpaca/
directory must NOT have __init__.py or it will shadow the real alpaca package.
"""
