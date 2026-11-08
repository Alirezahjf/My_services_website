from app.extensions import db
from .base import TimestampMixin


class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    english_name = db.Column(db.String(120))
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(80), default="sparkles")
    image_path = db.Column(db.String(255))
    is_visible = db.Column(db.Boolean, default=True, nullable=False, index=True)
    position = db.Column(db.Integer, default=0, nullable=False, index=True)

    products = db.relationship("Product", back_populates="category", foreign_keys="Product.category_id")

    @property
    def published_count(self):
        if hasattr(self, "_published_count"):
            return self._published_count
        return sum(1 for p in self.products if p.status == "published")
