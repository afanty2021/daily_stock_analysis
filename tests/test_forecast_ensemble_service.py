# -*- coding: utf-8 -*-
"""Tests for ForecastEnsembleService."""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from src.services.forecast_ensemble_service import (
    ForecastModelRegistry,
    ForecastModel,
    NaiveSeasonalModel,
    MovingAverageModel,
    ForecastEnsembleService,
)


class MockForecastModel(ForecastModel):
    """Mock model for testing."""

    def __init__(self, name: str, predictions: list):
        self._name = name
        self._predictions = predictions

    def predict(self, data: np.ndarray, horizon: int) -> dict:
        return {
            "predictions": self._predictions[:horizon],
            "trend": {"direction": "up"},
        }

    @property
    def name(self) -> str:
        return self._name


class TestForecastModelRegistry(unittest.TestCase):
    """Test model registry."""

    def test_register_and_get_model(self):
        """Test registering and retrieving models."""
        # Register a mock model
        ForecastModelRegistry.register("mock_test", MockForecastModel)

        # Check it's registered
        self.assertTrue(ForecastModelRegistry.is_registered("mock_test"))

        # Get the model class
        model_cls = ForecastModelRegistry.get("mock_test")
        self.assertEqual(model_cls, MockForecastModel)

    def test_list_models(self):
        """Test listing all registered models."""
        models = ForecastModelRegistry.list_models()
        self.assertIn("timesfm", models)
        self.assertIn("naive_seasonal", models)
        self.assertIn("moving_average", models)

    def test_get_nonexistent_model(self):
        """Test getting a model that doesn't exist."""
        with self.assertRaises(KeyError):
            ForecastModelRegistry.get("nonexistent_model")


class TestNaiveSeasonalModel(unittest.TestCase):
    """Test NaiveSeasonalModel."""

    def setUp(self):
        self.model = NaiveSeasonalModel(seasonality_period=5)

    def test_predict_with_sufficient_data(self):
        """Test prediction with sufficient historical data."""
        data = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
        horizon = 10

        result = self.model.predict(data, horizon)

        self.assertIn("predictions", result)
        self.assertIn("trend", result)
        self.assertEqual(len(result["predictions"]), horizon)
        self.assertEqual(result["metadata"]["model"], "naive_seasonal")
        self.assertEqual(result["metadata"]["seasonality_period"], 5)

    def test_predict_with_insufficient_data(self):
        """Test prediction with insufficient data."""
        data = np.array([100, 101, 102])
        horizon = 10

        result = self.model.predict(data, horizon)

        # Should use last value when data is insufficient
        self.assertEqual(len(result["predictions"]), horizon)
        # All predictions should be the last value
        self.assertTrue(all(p == 102 for p in result["predictions"]))

    def test_trend_calculation(self):
        """Test trend calculation."""
        data = np.arange(100, 110, dtype=float)
        horizon = 10

        result = self.model.predict(data, horizon)
        trend = result["trend"]

        self.assertIn("direction", trend)
        self.assertIn("strength", trend)
        self.assertIn("change_pct", trend)
        self.assertIn("start_value", trend)
        self.assertIn("end_value", trend)

    def test_model_name(self):
        """Test model name property."""
        self.assertEqual(self.model.name, "naive_seasonal")


class TestMovingAverageModel(unittest.TestCase):
    """Test MovingAverageModel."""

    def setUp(self):
        self.model = MovingAverageModel(window=5)

    def test_predict_with_sufficient_data(self):
        """Test prediction with sufficient data."""
        data = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
        horizon = 10

        result = self.model.predict(data, horizon)

        self.assertIn("predictions", result)
        self.assertEqual(len(result["predictions"]), horizon)
        # All predictions should be the same (average)
        self.assertTrue(all(p == result["predictions"][0] for p in result["predictions"]))
        self.assertEqual(result["metadata"]["model"], "moving_average")
        self.assertEqual(result["metadata"]["window"], 5)

    def test_predict_with_insufficient_data(self):
        """Test prediction with insufficient data."""
        data = np.array([100, 101, 102])
        horizon = 10

        result = self.model.predict(data, horizon)

        # Should use simple average
        expected_avg = np.mean(data)
        self.assertTrue(all(p == expected_avg for p in result["predictions"]))

    def test_model_name(self):
        """Test model name property."""
        self.assertEqual(self.model.name, "moving_average")


class TestForecastEnsembleService(unittest.TestCase):
    """Test ForecastEnsembleService."""

    def setUp(self):
        # Create mock models
        self.model1 = MockForecastModel("model1", [100, 101, 102, 103, 104])
        self.model2 = MockForecastModel("model2", [101, 102, 103, 104, 105])
        self.model3 = MockForecastModel("model3", [99, 100, 101, 102, 103])

    def test_simple_average_strategy(self):
        """Test simple average ensemble strategy."""
        ensemble = ForecastEnsembleService(
            models=[self.model1, self.model2, self.model3],
            strategy="simple",
        )

        data = np.arange(100, 200)
        result = ensemble.predict_ensemble(data, horizon=5)

        self.assertEqual(result["metadata"]["ensemble_strategy"], "simple")
        self.assertEqual(result["metadata"]["n_models"], 3)

        # Check simple average: (100+101+99)/3 = 100, (101+102+100)/3 = 101, etc.
        predictions = result["predictions"]
        self.assertAlmostEqual(predictions[0], 100.0)
        self.assertAlmostEqual(predictions[1], 101.0)
        self.assertAlmostEqual(predictions[2], 102.0)

    def test_median_strategy(self):
        """Test median ensemble strategy."""
        ensemble = ForecastEnsembleService(
            models=[self.model1, self.model2, self.model3],
            strategy="median",
        )

        data = np.arange(100, 200)
        result = ensemble.predict_ensemble(data, horizon=5)

        self.assertEqual(result["metadata"]["ensemble_strategy"], "median")

        # Check median: median([100, 101, 99]) = 100, median([101, 102, 100]) = 101, etc.
        predictions = result["predictions"]
        self.assertAlmostEqual(predictions[0], 100.0)
        self.assertAlmostEqual(predictions[1], 101.0)
        self.assertAlmostEqual(predictions[2], 102.0)

    def test_weighted_strategy(self):
        """Test weighted average ensemble strategy."""
        ensemble = ForecastEnsembleService(
            models=[self.model1, self.model2, self.model3],
            strategy="weighted",
        )

        data = np.arange(100, 200)
        result = ensemble.predict_ensemble(data, horizon=5)

        self.assertEqual(result["metadata"]["ensemble_strategy"], "weighted")
        # Weights should be present (even if equal for now)
        self.assertIsNotNone(result["metadata"]["weights"])

    def test_empty_models(self):
        """Test ensemble with no models."""
        ensemble = ForecastEnsembleService(models=[], strategy="simple")

        data = np.arange(100, 200)

        with self.assertRaises(ValueError):
            ensemble.predict_ensemble(data, horizon=5)

    def test_all_models_fail(self):
        """Test ensemble when all models fail."""
        # Create models that raise exceptions
        class FailingModel(ForecastModel):
            def predict(self, data, horizon):
                raise Exception("Model failed")

            @property
            def name(self):
                return "failing"

        ensemble = ForecastEnsembleService(
            models=[FailingModel(), FailingModel()],
            strategy="simple",
        )

        data = np.arange(100, 200)

        with self.assertRaises(ValueError):
            ensemble.predict_ensemble(data, horizon=5)

    def test_some_models_fail(self):
        """Test ensemble when some models fail."""
        # Create one failing and one successful model
        class FailingModel(ForecastModel):
            def predict(self, data, horizon):
                raise Exception("Model failed")

            @property
            def name(self):
                return "failing"

        ensemble = ForecastEnsembleService(
            models=[FailingModel(), self.model1],
            strategy="simple",
        )

        data = np.arange(100, 200)
        result = ensemble.predict_ensemble(data, horizon=5)

        # Should succeed with only the working model
        self.assertEqual(result["metadata"]["n_models"], 1)
        self.assertEqual(result["predictions"], [100, 101, 102, 103, 104])
        self.assertIn("errors", result["metadata"])

    def test_set_strategy(self):
        """Test changing ensemble strategy."""
        ensemble = ForecastEnsembleService(
            models=[self.model1, self.model2],
            strategy="simple",
        )

        # Change to median
        ensemble.set_strategy("median")
        self.assertEqual(ensemble.strategy, "median")

        # Change to weighted
        ensemble.set_strategy("weighted")
        self.assertEqual(ensemble.strategy, "weighted")

    def test_invalid_strategy(self):
        """Test setting an invalid strategy."""
        ensemble = ForecastEnsembleService(
            models=[self.model1],
            strategy="simple",
        )

        with self.assertRaises(ValueError):
            ensemble.set_strategy("invalid_strategy")

    def test_n_models_property(self):
        """Test n_models property."""
        ensemble = ForecastEnsembleService(
            models=[self.model1, self.model2, self.model3],
            strategy="simple",
        )

        self.assertEqual(ensemble.n_models, 3)

    def test_ensemble_trend_calculation(self):
        """Test trend calculation for ensemble predictions."""
        ensemble = ForecastEnsembleService(
            models=[self.model1, self.model2],
            strategy="simple",
        )

        data = np.arange(100, 200)
        result = ensemble.predict_ensemble(data, horizon=5)

        trend = result["trend"]
        self.assertIn("direction", trend)
        self.assertIn("strength", trend)
        self.assertIn("change_pct", trend)
        self.assertIn("start_value", trend)
        self.assertIn("end_value", trend)

        # Trend should be up (predictions are increasing)
        self.assertEqual(trend["direction"], "up")


if __name__ == "__main__":
    unittest.main()
