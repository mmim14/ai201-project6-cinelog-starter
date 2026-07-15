"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service. Mirrors the patterns in test_collection.py:
pytest fixtures for an isolated in-memory DB, and Arrange–Act–Assert bodies
wrapped in an app context.
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    get_watchlist,
    AlreadyInWatchListError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Basic add ───────────────────────────────────────────────────────────────

def test_add_to_watchlist_creates_entry(app, sample_user, sample_film):
    """
    Adding a valid film should create a WatchlistEntry in the database.
    """
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert entry is not None
        assert entry.user_id == sample_user
        assert entry.film_id == sample_film

        # Verify it persisted
        in_db = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert in_db is not None


# ── Deduplication ────────────────────────────────────────────────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyInWatchListError,
    not silently create a duplicate entry.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInWatchListError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        # Confirm only one entry exists
        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1

# ── Nonexistent film ─────────────────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error.
    """
    with app.app_context():
        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=999999)

# ── get_watchlist sorted by title ─────────────────────────────────────────────────

def test_get_watchlist_returns_films_sorted_by_title(app, sample_user):
    """
    get_watchlist() should return films sorted by title ascending,
    with watchlist metadata (date_added, public) attached.
    """
    with app.app_context():
        film_a = Film(title="Blade Runner", year=1982, genre="Sci-Fi")
        film_b = Film(title="Alien", year=1979, genre="Horror")
        db.session.add_all([film_a, film_b])
        db.session.commit()

        add_to_watchlist(user_id=sample_user, film_id=film_a.id)
        add_to_watchlist(user_id=sample_user, film_id=film_b.id)

        watchlist = get_watchlist(sample_user)
        titles = [f["title"] for f in watchlist]

        # Sorted by title ascending: Alien before Blade Runner
        assert titles == ["Alien", "Blade Runner"]
        assert "date_added" in watchlist[0]
        assert "public" in watchlist[0]