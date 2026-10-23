"""Fumée : chaque page s'importe, et l'application affiche l'écran de connexion sans erreur."""
import importlib

import pytest

PAGES = ["dashboard", "trading", "technical", "ai_markets", "auto_portfolio", "hedge_fund", "portfolio_upload", "optimizer",
         "reports", "leaderboard", "education", "events", "admin"]


@pytest.mark.parametrize("name", PAGES)
def test_page_imports(name):
    mod = importlib.import_module(f"pages.{name}")
    assert hasattr(mod, "render")


def test_app_login_screen():
    import os
    from streamlit.testing.v1 import AppTest
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    at = AppTest.from_file(os.path.join(root, "app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
