from pathlib import Path
from streamlit.testing.v1 import AppTest
import pytest


@pytest.mark.parametrize(
    "page",
    [
        "Overview",
        "Crowding monitor",
        "Holdings explorer",
        "Manager network",
        "Signal research",
        "Company research",
        "Data & methodology",
    ],
)
def test_dashboard_pages(page):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90)
    app.run()
    assert not app.exception
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception


def test_no_match_and_zero_weights():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()
    app.sidebar.radio[0].set_value("Holdings explorer").run()
    app.text_input[0].set_value("not-a-real-manager").run()
    assert not app.exception
    for slider in app.sidebar.slider:
        slider.set_value(0.0)
    app.run()
    assert not app.exception
    assert app.error
