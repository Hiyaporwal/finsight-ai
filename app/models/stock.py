from app.extensions import db
from app.models.user import utcnow


class Stock(db.Model):
    """Metadata for supported NSE stocks. Prices are fetched/cached, not stored here."""
    __tablename__ = "stocks"

    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(30), nullable=False, unique=True, index=True)  # Yahoo symbol
    name = db.Column(db.String(150), nullable=False)
    sector = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class Watchlist(db.Model):
    __tablename__ = "watchlists"
    __table_args__ = (db.UniqueConstraint("user_id", "stock_id", name="uq_watchlist_user_stock"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id", ondelete="CASCADE"),
                         nullable=False)
    added_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    stock = db.relationship("Stock")