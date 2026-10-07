import logging
import os
from flask import Flask, render_template
from app.config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter

SUPPORTED_STOCKS = [
    ("RELIANCE.NS", "Reliance Industries", "Energy / Conglomerate"),
    ("TCS.NS", "Tata Consultancy Services", "IT Services"),
    ("HDFCBANK.NS", "HDFC Bank", "Banking"),
    ("ICICIBANK.NS", "ICICI Bank", "Banking"),
    ("INFY.NS", "Infosys", "IT Services"),
    ("SBIN.NS", "State Bank of India", "Banking"),
    ("LT.NS", "Larsen & Toubro", "Infrastructure / Engineering"),
    ("TMPV.NS", "Tata Motors (Passenger Vehicles)", "Automobiles"),
    ("BHARTIARTL.NS", "Bharti Airtel", "Telecom"),
    ("ITC.NS", "ITC", "FMCG / Conglomerate"),
]


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and set it.")

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app import models  # noqa: F401
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.stocks import stocks_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(stocks_bp)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.cli.command("seed-stocks")
    def seed_stocks():
        """Insert the ten supported stocks (idempotent)."""
        from app.models.stock import Stock
        added = 0
        for symbol, name, sector in SUPPORTED_STOCKS:
            if not Stock.query.filter_by(symbol=symbol).first():
                db.session.add(Stock(symbol=symbol, name=name, sector=sector))
                added += 1
        db.session.commit()
        print(f"Seeded {added} new stocks.")

    return app