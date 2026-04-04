"""
Unit tests for face_authenticator.py
"""

import numpy as np
import pytest

from modules.face_authenticator import compare_embeddings


class TestCompareEmbeddings:
    """Test suite for the compare_embeddings function."""

    def test_identical_embeddings_match(self):
        """Two identical embeddings should match (distance = 0)."""
        embedding = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
        embedding /= np.linalg.norm(embedding)  # normalise

        assert compare_embeddings(embedding, embedding, threshold=0.6)

    def test_very_similar_embeddings_match(self):
        """Two very similar embeddings should match."""
        rng = np.random.default_rng(42)
        base = rng.standard_normal(128).astype(np.float64)
        base /= np.linalg.norm(base)

        # Small perturbation to create a similar embedding
        similar = base + rng.standard_normal(128) * 0.02
        similar /= np.linalg.norm(similar)

        distance = float(np.linalg.norm(base - similar))
        assert distance < 0.3, "Test setup: similar vectors should be close"
        assert compare_embeddings(base, similar, threshold=0.6)

    def test_dissimilar_embeddings_do_not_match(self):
        """Two dissimilar embeddings should not match."""
        rng = np.random.default_rng(42)
        v1 = rng.standard_normal(128).astype(np.float64)
        v1 /= np.linalg.norm(v1)

        v2 = rng.standard_normal(128).astype(np.float64)
        v2 /= np.linalg.norm(v2)

        distance = float(np.linalg.norm(v1 - v2))
        assert distance > 0.8, "Test setup: random vectors should be far apart"
        assert not compare_embeddings(v1, v2, threshold=0.6)

    def test_threshold_boundary(self):
        """Test threshold boundary conditions."""
        rng = np.random.default_rng(42)
        v1 = rng.standard_normal(128).astype(np.float64)
        v1 /= np.linalg.norm(v1)

        v2 = v1 + rng.standard_normal(128) * 0.1
        v2 /= np.linalg.norm(v2)

        distance = float(np.linalg.norm(v1 - v2))

        # Should match with a threshold above the distance
        assert compare_embeddings(v1, v2, threshold=distance + 0.01)

        # Should not match with a threshold below the distance
        assert not compare_embeddings(v1, v2, threshold=distance - 0.01)

    def test_shape_mismatch_raises_error(self):
        """Embeddings with different shapes should raise ValueError."""
        v1 = np.array([0.1, 0.2, 0.3], dtype=np.float64)
        v2 = np.array([0.1, 0.2], dtype=np.float64)

        with pytest.raises(ValueError, match="shape mismatch"):
            compare_embeddings(v1, v2)

    def test_invalid_threshold_raises_error(self):
        """Non-positive threshold should raise ValueError."""
        v = np.array([0.1, 0.2, 0.3], dtype=np.float64)

        with pytest.raises(ValueError, match="threshold must be > 0"):
            compare_embeddings(v, v, threshold=0.0)

        with pytest.raises(ValueError, match="threshold must be > 0"):
            compare_embeddings(v, v, threshold=-0.5)
