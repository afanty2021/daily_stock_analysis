# -*- coding: utf-8 -*-
"""Tests for ForecastAccuracyService."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import numpy as np

from src.config import Config
from src.storage import DatabaseManager, ForecastRecord
from src.services.forecast_accuracy_service import ForecastAccuracyService


class TestCalculateMetrics(unittest.TestCase):
    """Test _calculate_metrics with known values."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_metrics.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = ForecastAccuracyService(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        self._temp_dir.cleanup()

    def test_perfect_prediction(self):
        """Perfect predictions should have zero error."""
        predictions = np.array([100.0, 101.0, 102.0])
        actuals = np.array([100.0, 101.0, 102.0])
        metrics = self.service._calculate_metrics(predictions, actuals)
        self.assertAlmostEqual(metrics["mae"], 0.0)
        self.assertAlmostEqual(metrics["mape"], 0.0)
        self.assertAlmostEqual(metrics["rmse"], 0.0)

    def test_known_values(self):
        """Test with known values for MAE, MAPE, RMSE."""
        predictions = np.array([100.0, 110.0, 120.0])
        actuals = np.array([105.0, 115.0, 125.0])
        metrics = self.service._calculate_metrics(predictions, actuals)

        # MAE = mean(|105-100|, |115-110|, |125-120|) = 5.0
        self.assertAlmostEqual(metrics["mae"], 5.0, places=3)

        # MAPE = mean(|5/105|, |5/115|, |5/125|) = mean(0.04762, 0.04348, 0.04) ~ 0.0437
        expected_mape = np.mean(np.array([5/105, 5/115, 5/125]))
        self.assertAlmostEqual(metrics["mape"], round(expected_mape, 4), places=3)

        # RMSE = sqrt(mean(25, 25, 25)) = 5.0
        self.assertAlmostEqual(metrics["rmse"], 5.0, places=3)

    def test_single_point(self):
        """Test with single data point."""
        predictions = np.array([100.0])
        actuals = np.array([110.0])
        metrics = self.service._calculate_metrics(predictions, actuals)
        self.assertAlmostEqual(metrics["mae"], 10.0)
        self.assertAlmostEqual(metrics["mape"], round(10.0 / 110.0, 4))
        self.assertAlmostEqual(metrics["rmse"], 10.0)

    def test_zero_actuals(self):
        """Test with zero actual values (should handle division by zero)."""
        predictions = np.array([1.0, 2.0])
        actuals = np.array([0.0, 0.0])
        metrics = self.service._calculate_metrics(predictions, actuals)
        self.assertIsNotNone(metrics["mae"])
        self.assertIsNone(metrics["mape"])  # MAPE undefined for zero actuals
        self.assertIsNotNone(metrics["rmse"])


class TestRecordForecast(unittest.TestCase):
    """Test record_forecast method."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_record.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = ForecastAccuracyService(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        self._temp_dir.cleanup()

    def test_record_with_numpy_array(self):
        """Test recording a forecast with numpy array input."""
        result = self.service.record_forecast(
            query_id="q001",
            stock_code="600519",
            stock_name="贵州茅台",
            current_price=1800.0,
            point_forecast=np.array([1810.0, 1820.0, 1830.0]),
            quantile_forecast=np.array([[1800, 1820], [1810, 1830], [1820, 1840]]),
            horizon=3,
            context_length=128,
            model_version="timesfm-2.0",
            trend_direction="up",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.query_id, "q001")
        self.assertEqual(result.stock_code, "600519")
        self.assertEqual(result.current_price, 1800.0)

        # Verify data in DB
        with self.db.get_session() as session:
            record = session.query(ForecastRecord).filter_by(query_id="q001").first()
            self.assertIsNotNone(record)
            self.assertEqual(json.loads(record.point_forecast), [1810.0, 1820.0, 1830.0])

    def test_record_with_list(self):
        """Test recording a forecast with list input."""
        result = self.service.record_forecast(
            query_id="q002",
            stock_code="hk00700",
            stock_name="腾讯控股",
            current_price=350.0,
            point_forecast=[355.0, 360.0],
            horizon=2,
            context_length=64,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.stock_code, "hk00700")

    def test_record_forecast_failure_returns_none(self):
        """Test that recording failure returns None gracefully."""
        # Use a closed/broken DB manager by mocking save_forecast to raise
        with patch.object(self.service.repo, 'save_forecast', side_effect=Exception("DB error")):
            result = self.service.record_forecast(
                query_id="q003",
                stock_code="600519",
                stock_name="Test",
                current_price=100.0,
                point_forecast=[101.0],
                horizon=1,
                context_length=64,
            )
            self.assertIsNone(result)


class TestEvaluatePending(unittest.TestCase):
    """Test evaluate_pending with mocked data provider."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_eval.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = ForecastAccuracyService(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        self._temp_dir.cleanup()

    def test_evaluate_pending_no_records(self):
        """Test evaluate_pending with no pending records."""
        result = self.service.evaluate_pending()
        self.assertEqual(result["total_pending"], 0)
        self.assertEqual(result["evaluated"], 0)

    @patch("data_provider.base.DataFetcherManager")
    def test_evaluate_pending_with_records(self, mock_fetcher_cls):
        """Test evaluate_pending with mock data provider."""
        # Seed a pending forecast record
        old_date = datetime.now() - timedelta(days=30)
        with self.db.session_scope() as session:
            record = ForecastRecord(
                query_id="q_eval",
                stock_code="600519",
                stock_name="贵州茅台",
                prediction_date=old_date,
                current_price=100.0,
                point_forecast=json.dumps([105.0, 110.0, 115.0]),
                quantile_forecast=None,
                horizon=3,
                context_length=128,
                model_version="timesfm-2.0",
                trend_direction="up",
                evaluated=False,
                created_at=old_date,
            )
            session.add(record)
            session.flush()
            record_id = record.id

        # Mock data provider
        import pandas as pd
        mock_df = pd.DataFrame({
            "date": pd.date_range(start=old_date, periods=5),
            "close": [101.0, 106.0, 112.0, 116.0, 118.0],
        })
        mock_fetcher = MagicMock()
        mock_fetcher.get_daily_data.return_value = (mock_df, "mock")
        mock_fetcher_cls.return_value = mock_fetcher

        result = self.service.evaluate_pending()
        self.assertEqual(result["total_pending"], 1)
        self.assertEqual(result["evaluated"], 1)
        self.assertEqual(result["errors"], 0)

        # Verify the record is now evaluated
        with self.db.get_session() as session:
            updated = session.query(ForecastRecord).get(record_id)
            self.assertTrue(updated.evaluated)


class TestAccuracyReport(unittest.TestCase):
    """Test accuracy report generation."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_report.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = ForecastAccuracyService(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        self._temp_dir.cleanup()

    def test_empty_report(self):
        """Test report with no data."""
        report = self.service.get_accuracy_report(days=30)
        self.assertIn("summary", report)
        self.assertIn("recent_forecasts", report)
        self.assertIn("generated_at", report)
        self.assertEqual(report["summary"]["total_evaluations"], 0)


class TestRealtimeForecastCache(unittest.TestCase):
    """Test real-time forecast caching functionality."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_cache.db")
        os.environ["DATABASE_PATH"] = self._db_path
        # Enable realtime mode for testing
        os.environ["TIMESFM_REALTIME_UPDATE_ENABLED"] = "true"
        os.environ["TIMESFM_CACHE_TTL_MINUTES"] = "60"
        os.environ["TIMESFM_UPDATE_ON_PRICE_CHANGE_PCT"] = "2.0"
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = ForecastAccuracyService(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        del os.environ["TIMESFM_REALTIME_UPDATE_ENABLED"]
        del os.environ["TIMESFM_CACHE_TTL_MINUTES"]
        del os.environ["TIMESFM_UPDATE_ON_PRICE_CHANGE_PCT"]
        self._temp_dir.cleanup()

    def test_cache_forecast_and_retrieve(self):
        """Test caching and retrieving a forecast."""
        stock_code = "600519"
        forecast_data = {
            "predictions": [1810.0, 1820.0, 1830.0],
            "trend": {"direction": "up", "strength": 0.8},
            "metadata": {"context_len": 256, "horizon_len": 60},
        }
        current_price = 1800.0

        # Cache the forecast
        self.service.cache_forecast(stock_code, forecast_data, current_price)

        # Retrieve it
        cached = self.service.get_cached_forecast(stock_code)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["forecast_data"], forecast_data)
        self.assertEqual(cached["current_price"], current_price)
        self.assertIn("cached_at", cached)

    def test_cache_miss(self):
        """Test cache miss for non-existent stock."""
        cached = self.service.get_cached_forecast("999999")
        self.assertIsNone(cached)

    def test_cache_invalidation_single_stock(self):
        """Test invalidating cache for a single stock."""
        stock_code = "600519"
        forecast_data = {"predictions": [1810.0], "trend": {}}
        self.service.cache_forecast(stock_code, forecast_data, 1800.0)

        # Verify it's cached
        cached = self.service.get_cached_forecast(stock_code)
        self.assertIsNotNone(cached)

        # Invalidate
        self.service.invalidate_cache(stock_code)

        # Verify it's gone
        cached = self.service.get_cached_forecast(stock_code)
        self.assertIsNone(cached)

    def test_cache_invalidation_all(self):
        """Test invalidating all cache."""
        # Cache multiple stocks
        for code in ["600519", "000001", "hk00700"]:
            self.service.cache_forecast(code, {"predictions": [100.0]}, 100.0)

        # Verify all are cached
        stats = self.service.get_cache_stats()
        self.assertEqual(stats["total_cached"], 3)

        # Invalidate all
        self.service.invalidate_cache()

        # Verify all are gone
        stats = self.service.get_cache_stats()
        self.assertEqual(stats["total_cached"], 0)

    def test_cache_stale_detection(self):
        """Test that stale cache is not returned."""
        stock_code = "600519"
        forecast_data = {"predictions": [1810.0], "trend": {}}

        # Set a very short TTL for testing
        self.service.cache_ttl_minutes = 0
        self.service.cache_forecast(stock_code, forecast_data, 1800.0)

        # Cache should be stale immediately
        cached = self.service.get_cached_forecast(stock_code)
        self.assertIsNone(cached)

    def test_price_change_threshold(self):
        """Test cache invalidation on significant price change."""
        stock_code = "600519"
        forecast_data = {"predictions": [1810.0], "trend": {}}
        original_price = 1800.0

        # Cache forecast
        self.service.cache_forecast(stock_code, forecast_data, original_price)

        # Small price change should use cache
        cached = self.service.get_cached_forecast(stock_code, current_price=1810.0)
        self.assertIsNotNone(cached)  # 0.56% change < 2% threshold

        # Large price change should invalidate cache
        cached = self.service.get_cached_forecast(stock_code, current_price=1900.0)
        self.assertIsNone(cached)  # 5.56% change > 2% threshold

    def test_cache_stats(self):
        """Test cache statistics."""
        # Cache some stocks
        self.service.cache_forecast("600519", {"predictions": [1.0]}, 100.0)
        self.service.cache_forecast("000001", {"predictions": [2.0]}, 200.0)

        stats = self.service.get_cache_stats()
        self.assertEqual(stats["total_cached"], 2)
        self.assertEqual(stats["fresh_count"], 2)
        self.assertEqual(stats["stale_count"], 0)
        self.assertTrue(stats["realtime_enabled"])
        self.assertEqual(stats["cache_ttl_minutes"], 60)
        self.assertEqual(stats["price_change_threshold_pct"], 2.0)

    def test_update_forecast_if_stale_with_mock(self):
        """Test update_forecast_if_stale with mocked TimesFM service."""
        from unittest.mock import MagicMock, patch

        stock_code = "600519"
        current_price = 1800.0
        historical_data = np.array([1700.0, 1750.0, 1780.0, 1790.0, 1800.0] * 10)  # 50 points

        # Mock TimesFM service
        mock_timesfm = MagicMock()
        mock_result = {
            "predictions": [1810.0, 1820.0, 1830.0],
            "trend": {"direction": "up"},
            "metadata": {},
        }
        mock_timesfm.predict.return_value = mock_result

        # First call should generate new forecast
        result = self.service.update_forecast_if_stale(
            stock_code=stock_code,
            current_price=current_price,
            timesfm_service=mock_timesfm,
            historical_data=historical_data,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result, mock_result)
        mock_timesfm.predict.assert_called_once()

        # Second call should use cache
        mock_timesfm.predict.reset_mock()
        result = self.service.update_forecast_if_stale(
            stock_code=stock_code,
            current_price=current_price,
            timesfm_service=mock_timesfm,
            historical_data=historical_data,
        )

        self.assertIsNotNone(result)
        mock_timesfm.predict.assert_not_called()  # Should use cache

    def test_disabled_realtime_mode(self):
        """Test that caching is disabled when realtime is off."""
        # Disable realtime
        self.service.realtime_enabled = False

        stock_code = "600519"
        forecast_data = {"predictions": [1810.0], "trend": {}}

        # Cache should be ignored
        self.service.cache_forecast(stock_code, forecast_data, 1800.0)
        cached = self.service.get_cached_forecast(stock_code)
        self.assertIsNone(cached)


if __name__ == "__main__":
    unittest.main()
