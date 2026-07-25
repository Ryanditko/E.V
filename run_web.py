"""Entry point for E.V.'s web interface (use her from any browser).

    python run_web.py

Requires EV_WEB_TOKEN in .env. Reuses the same brain/memory as the Telegram bot.
"""

from ev.interfaces.web import run

if __name__ == "__main__":
    run()
