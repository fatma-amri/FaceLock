"""
Unit tests for database.py
"""

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from modules.database import (add_user, delete_user, get_all_users,
                              list_user_names)


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


class TestDatabaseRoundTrip:
    """Test suite for database add/retrieve/delete operations."""

    def test_add_and_retrieve_user(self, temp_db):
        """Add a user and verify they can be retrieved."""
        name = "Alice"
        embedding = np.random.randn(128).astype(np.float64)
        embedding /= np.linalg.norm(embedding)

        add_user(name, embedding, db_path=temp_db)
        users = get_all_users(db_path=temp_db)

        assert len(users) == 1
        retrieved_name, retrieved_embedding = users[0]
        assert retrieved_name == name
        assert retrieved_embedding.shape == embedding.shape
        assert np.allclose(retrieved_embedding, embedding, atol=1e-10)

    def test_add_multiple_users(self, temp_db):
        """Add multiple users and verify all are retrievable."""
        users_data = [
            ("Alice", np.random.randn(128).astype(np.float64)),
            ("Bob", np.random.randn(128).astype(np.float64)),
            ("Charlie", np.random.randn(128).astype(np.float64)),
        ]

        for name, emb in users_data:
            emb /= np.linalg.norm(emb)
            add_user(name, emb, db_path=temp_db)

        retrieved = get_all_users(db_path=temp_db)
        assert len(retrieved) == 3

        retrieved_names = {name for name, _ in retrieved}
        expected_names = {name for name, _ in users_data}
        assert retrieved_names == expected_names

    def test_upsert_existing_user(self, temp_db):
        """Re-enrolling a user should replace their embedding."""
        name = "Alice"
        emb1 = np.random.randn(128).astype(np.float64)
        emb1 /= np.linalg.norm(emb1)

        emb2 = np.random.randn(128).astype(np.float64)
        emb2 /= np.linalg.norm(emb2)

        # Add first embedding
        add_user(name, emb1, db_path=temp_db)
        users = get_all_users(db_path=temp_db)
        assert len(users) == 1

        # Replace with second embedding
        add_user(name, emb2, db_path=temp_db)
        users = get_all_users(db_path=temp_db)
        assert len(users) == 1, "User count should remain 1 after upsert"
        _, second_retrieved = users[0]

        # Verify the embedding changed
        assert np.allclose(second_retrieved, emb2, atol=1e-10)

    def test_delete_user(self, temp_db):
        """Delete a user and verify they are removed."""
        add_user("Alice", np.random.randn(128).astype(np.float64), db_path=temp_db)
        add_user("Bob", np.random.randn(128).astype(np.float64), db_path=temp_db)

        users_before = get_all_users(db_path=temp_db)
        assert len(users_before) == 2

        delete_user("Alice", db_path=temp_db)
        users_after = get_all_users(db_path=temp_db)

        assert len(users_after) == 1
        assert users_after[0][0] == "Bob"

    def test_list_user_names(self, temp_db):
        """List user names should return sorted list of names."""
        names = ["Charlie", "Alice", "Bob"]
        for name in names:
            add_user(name, np.random.randn(128).astype(np.float64), db_path=temp_db)

        retrieved_names = list_user_names(db_path=temp_db)
        assert retrieved_names == sorted(names)

    def test_add_user_invalid_name(self, temp_db):
        """Adding a user with empty name should raise ValueError."""
        embedding = np.random.randn(128).astype(np.float64)

        with pytest.raises(ValueError, match="non-empty string"):
            add_user("", embedding, db_path=temp_db)

    def test_add_user_invalid_embedding_shape(self, temp_db):
        """Adding a user with multi-dimensional embedding should raise ValueError."""
        embedding_2d = np.random.randn(128, 2).astype(np.float64)

        with pytest.raises(ValueError, match="1-D"):
            add_user("Alice", embedding_2d, db_path=temp_db)
