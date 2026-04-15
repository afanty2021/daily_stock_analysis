# -*- coding: utf-8 -*-
"""Tests for ForecastRepo."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from src.config import Config
from src.storage import DatabaseManager, ForecastRecord, ForecastEvaluation
from src.repositories.forecast_repo import ForecastRepo


class TestForecastRepoSaveAndGet(unittest.TestCase):
    """Test save and retrieve forecast records."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_repo.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.repo = ForecastRepo(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        self._temp_dir.cleanup()

    def test_save_forecast(self):
        """Test saving a forecast record."""
        record = self.repo.save_forecast(
            query_id="q_save_1",
            stock_code="600519",
            stock_name="贵州茅台",
            current_price=1800.0,
            point_forecast=json.dumps([1810.0, 1820.0, 1830.0]),
            quantile_forecast=json.dumps([[1800, 1820], [1810, 1830], [1820, 1840]]),
            horizon=3,
            context_length=128,
            model_version="timesfm-2.0",
            trend_direction="up",
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.query_id, "q_save_1")
        self.assertEqual(record.stock_code, "600519")
        self.assertEqual(record.current_price, 1800.0)
        self.assertFalse(record.evaluated)

    def test_get_pending_evaluations_empty(self):
        """Test getting pending evaluations when none exist."""
        pending = self.repo.get_pending_evaluations()
        self.assertEqual(len(pending), 0)

    def test_get_pending_evaluations_with_records(self):
        """Test getting pending evaluations with seeded records."""
        old_date = datetime.now() - timedelta(days=30)
        recent_date = datetime.now() - timedelta(days=2)

        # Old unevaluated record (should be pending)
        with self.db.session_scope() as session:
            session.add(ForecastRecord(
                query_id="q_pending_old",
                stock_code="600519",
                stock_name="Test1",
                prediction_date=old_date,
                current_price=100.0,
                point_forecast=json.dumps([101.0, 102.0]),
                horizon=2,
                context_length=64,
                evaluated=False,
                created_at=old_date,
            ))
            # Recent unevaluated record (too recent, should NOT be pending with min_age_days=7)
            session.add(ForecastRecord(
                query_id="q_pending_recent",
                stock_code="600519",
                stock_name="Test2",
                prediction_date=recent_date,
                current_price=200.0,
                point_forecast=json.dumps([201.0, 202.0]),
                horizon=2,
                context_length=64,
                evaluated=False,
                created_at=recent_date,
            ))
            # Old evaluated record (should NOT be pending)
            session.add(ForecastRecord(
                query_id="q_evaluated",
                stock_code="600519",
                stock_name="Test3",
                prediction_date=old_date,
                current_price=300.0,
                point_forecast=json.dumps([301.0, 302.0]),
                horizon=2,
                context_length=64,
                evaluated=True,
                created_at=old_date,
            ))

        pending = self.repo.get_pending_evaluations(min_age_days=7)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].query_id, "q_pending_old")

    def test_save_evaluation(self):
        """Test saving an evaluation result."""
        # First create a forecast record
        record = self.repo.save_forecast(
            query_id="q_eval",
            stock_code="600519",
            stock_name="Test",
            current_price=100.0,
            point_forecast=json.dumps([101.0, 102.0, 103.0]),
            quantile_forecast=None,
            horizon=3,
            context_length=64,
            model_version="timesfm-2.0",
            trend_direction="up",
        )
        self.assertIsNotNone(record)

        # Save evaluation
        evaluation = self.repo.save_evaluation(
            forecast_record_id=record.id,
            actual_prices=json.dumps([102.0, 103.0, 104.0]),
            mae=1.0,
            mape=0.0098,
            rmse=1.0,
            direction_correct=True,
        )
        self.assertIsNotNone(evaluation)
        self.assertEqual(evaluation.forecast_record_id, record.id)
        self.assertAlmostEqual(evaluation.mae, 1.0)
        self.assertTrue(evaluation.direction_correct)

        # Verify the record is now marked as evaluated
        with self.db.get_session() as session:
            updated = session.query(ForecastRecord).get(record.id)
            self.assertTrue(updated.evaluated)


class TestForecastRepoSummary(unittest.TestCase):
    """Test accuracy summary queries."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_summary.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.repo = ForecastRepo(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        self._temp_dir.cleanup()

    def test_accuracy_summary_empty(self):
        """Test accuracy summary with no data."""
        summary = self.repo.get_accuracy_summary(days=30)
        self.assertEqual(summary["total_evaluations"], 0)
        self.assertIsNone(summary["avg_mape"])

    def test_accuracy_summary_with_data(self):
        """Test accuracy summary with seeded evaluations."""
        now = datetime.now()

        # Create forecast records and evaluations
        with self.db.session_scope() as session:
            # Stock 1
            r1 = ForecastRecord(
                query_id="q_s1",
                stock_code="600519",
                stock_name="贵州茅台",
                prediction_date=now - timedelta(days=20),
                current_price=100.0,
                point_forecast=json.dumps([105.0, 110.0]),
                horizon=2,
                context_length=64,
                evaluated=True,
                created_at=now - timedelta(days=20),
            )
            session.add(r1)
            session.flush()

            session.add(ForecastEvaluation(
                forecast_record_id=r1.id,
                actual_prices=json.dumps([104.0, 108.0]),
                mae=1.5,
                mape=0.014,
                rmse=1.8,
                direction_correct=True,
                evaluated_at=now - timedelta(days=10),
            ))

            # Stock 2
            r2 = ForecastRecord(
                query_id="q_s2",
                stock_code="hk00700",
                stock_name="腾讯控股",
                prediction_date=now - timedelta(days=15),
                current_price=350.0,
                point_forecast=json.dumps([360.0, 370.0]),
                horizon=2,
                context_length=64,
                evaluated=True,
                created_at=now - timedelta(days=15),
            )
            session.add(r2)
            session.flush()

            session.add(ForecastEvaluation(
                forecast_record_id=r2.id,
                actual_prices=json.dumps([340.0, 330.0]),
                mae=30.0,
                mape=0.0857,
                rmse=30.5,
                direction_correct=False,
                evaluated_at=now - timedelta(days=5),
            ))

        summary = self.repo.get_accuracy_summary(days=30)
        self.assertEqual(summary["total_evaluations"], 2)
        self.assertIsNotNone(summary["avg_mape"])
        self.assertEqual(summary["direction_total"], 2)
        self.assertEqual(summary["direction_correct"], 1)
        self.assertAlmostEqual(summary["direction_accuracy"], 0.5)

    def test_stock_accuracy(self):
        """Test per-stock accuracy query."""
        now = datetime.now()

        with self.db.session_scope() as session:
            r1 = ForecastRecord(
                query_id="q_stock1",
                stock_code="600519",
                stock_name="贵州茅台",
                prediction_date=now - timedelta(days=60),
                current_price=100.0,
                point_forecast=json.dumps([105.0]),
                horizon=1,
                context_length=64,
                evaluated=True,
                created_at=now - timedelta(days=60),
            )
            session.add(r1)
            session.flush()

            session.add(ForecastEvaluation(
                forecast_record_id=r1.id,
                actual_prices=json.dumps([106.0]),
                mae=1.0,
                mape=0.0094,
                rmse=1.0,
                direction_correct=True,
                evaluated_at=now - timedelta(days=30),
            ))

        # Query for stock 600519
        result = self.repo.get_stock_accuracy(stock_code="600519", days=90)
        self.assertEqual(result["stock_code"], "600519")
        self.assertEqual(result["total_evaluations"], 1)
        self.assertIsNotNone(result["avg_mape"])

        # Query for stock with no data
        result2 = self.repo.get_stock_accuracy(stock_code="000001", days=90)
        self.assertEqual(result2["total_evaluations"], 0)
        self.assertIsNone(result2["avg_mape"])


class TestGetRecentForecasts(unittest.TestCase):
    """Test get_recent_forecasts query."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_recent.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.repo = ForecastRepo(db_manager=self.db)

    def tearDown(self):
        DatabaseManager.reset_instance()
        Config._instance = None
        del os.environ["DATABASE_PATH"]
        self._temp_dir.cleanup()

    def test_get_recent_forecasts_empty(self):
        """Test with no records."""
        result = self.repo.get_recent_forecasts(limit=10)
        self.assertEqual(len(result), 0)

    def test_get_recent_forecasts_ordered(self):
        """Test that recent forecasts are ordered by created_at desc."""
        now = datetime.now()
        with self.db.session_scope() as session:
            session.add(ForecastRecord(
                query_id="q_old",
                stock_code="600519",
                stock_name="Old",
                prediction_date=now - timedelta(days=10),
                current_price=100.0,
                point_forecast=json.dumps([101.0]),
                horizon=1,
                context_length=64,
                created_at=now - timedelta(days=10),
            ))
            session.add(ForecastRecord(
                query_id="q_new",
                stock_code="hk00700",
                stock_name="New",
                prediction_date=now,
                current_price=350.0,
                point_forecast=json.dumps([355.0]),
                horizon=1,
                context_length=64,
                created_at=now,
            ))

        result = self.repo.get_recent_forecasts(limit=10)
        self.assertEqual(len(result), 2)
        # Most recent first
        self.assertEqual(result[0]["stock_code"], "hk00700")
        self.assertEqual(result[1]["stock_code"], "600519")

    def test_get_recent_forecasts_limit(self):
        """Test that limit parameter works."""
        now = datetime.now()
        with self.db.session_scope() as session:
            for i in range(5):
                session.add(ForecastRecord(
                    query_id=f"q_limit_{i}",
                    stock_code="600519",
                    stock_name="Test",
                    prediction_date=now,
                    current_price=100.0 + i,
                    point_forecast=json.dumps([101.0]),
                    horizon=1,
                    context_length=64,
                    created_at=now,
                ))

        result = self.repo.get_recent_forecasts(limit=3)
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
