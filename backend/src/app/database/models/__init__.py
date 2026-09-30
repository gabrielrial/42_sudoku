"""Every ORM model, imported in one place.

A model only registers its table in ``Base.metadata`` when its module is
imported. Alembic's autogenerate compares that metadata with the database, so
``migrations/env.py`` imports this package: a model missing from here is a
table Alembic cannot see. Add each new model below.
"""

from app.database.models.users import User

__all__ = ["User"]
