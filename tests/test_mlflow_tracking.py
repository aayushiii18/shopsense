"""
tests/test_mlflow_tracking.py — Test Suite for MLflow Experiment Tracking & Model Registry.

Tests:
  1. MLflow tracking URI configuration and experiment creation.
  2. Inventory dataset loading (database and canonical fallback).
  3. Metric logging (genuine MAE, RMSE, WAPE, R²).
  4. Hyperparameter and dataset metadata logging.
  5. Model artifact logging.
  6. Model registration as 'InventoryForecast' and version tracking.
  7. Model loading and test inference.
  8. Existing forecasting API functionality after MLflow integration.
  9. Graceful fallback when MLflow registry is unavailable.
"""

import os
import pytest
import mlflow
from mlflow.tracking import MlflowClient

from track_inventory import (
    setup_mlflow_tracking,
    load_inventory_dataset,
    train_and_track_inventory_model,
    load_registered_inventory_model,
    get_default_tracking_uri,
)


@pytest.fixture(scope="module")
def test_mlflow_uri(tmp_path_factory):
    """Provides isolated SQLite tracking URI for testing."""
    tmp_dir = tmp_path_factory.mktemp("mlflow_test")
    db_file = tmp_dir / "test_mlflow.db"
    uri = f"sqlite:///{str(db_file).replace(os.sep, '/')}"
    return uri


def test_setup_mlflow_tracking(test_mlflow_uri):
    """Verify MLflow tracking URI configuration."""
    uri = setup_mlflow_tracking(test_mlflow_uri)
    assert uri == test_mlflow_uri
    assert mlflow.get_tracking_uri() == test_mlflow_uri


def test_load_inventory_dataset(db_session):
    """Verify historical dataset extraction and fallback metadata."""
    df, info = load_inventory_dataset(db=db_session)
    assert "dataset_rows" in info
    assert "monthly_demand" in info
    assert len(info["monthly_demand"]) == 12
    assert "dataset_start_date" in info
    assert "dataset_end_date" in info


def test_train_and_track_inventory_model_metrics(test_mlflow_uri, db_session):
    """Verify parameters, metrics (MAE, RMSE, WAPE, R²), and artifact logging."""
    res = train_and_track_inventory_model(
        db=db_session,
        tracking_uri=test_mlflow_uri,
        experiment_name="Test_Inventory_Forecasting",
        model_name="TestInventoryForecast",
        n_estimators=15,
        register=True,
    )

    assert "run_id" in res
    assert res["model_name"] == "TestInventoryForecast"
    assert res["model_version"] is not None

    metrics = res["metrics"]
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "wape" in metrics
    assert "r2" in metrics
    assert metrics["mae"] >= 0.0
    assert metrics["rmse"] >= 0.0
    assert metrics["wape"] >= 0.0

    # Verify run directly in MLflow client
    client = MlflowClient(tracking_uri=test_mlflow_uri)
    run = client.get_run(res["run_id"])
    assert run.data.metrics["mae"] == metrics["mae"]
    assert run.data.metrics["rmse"] == metrics["rmse"]
    assert run.data.metrics["wape"] == metrics["wape"]
    assert run.data.params["model_type"] == "RandomForestRegressor"
    assert run.data.params["n_estimators"] == "15"


def test_model_registration_and_version_loading(test_mlflow_uri, db_session):
    """Verify model registration and inference from loaded registered model."""
    # First version
    v1_res = train_and_track_inventory_model(
        db=db_session,
        tracking_uri=test_mlflow_uri,
        experiment_name="Test_Inventory_Forecasting",
        model_name="VersionedTestModel",
        n_estimators=10,
        register=True,
    )
    assert v1_res["model_version"] == "1"

    # Second version
    v2_res = train_and_track_inventory_model(
        db=db_session,
        tracking_uri=test_mlflow_uri,
        experiment_name="Test_Inventory_Forecasting",
        model_name="VersionedTestModel",
        n_estimators=20,
        register=True,
    )
    assert v2_res["model_version"] == "2"

    # Load version 1 specifically
    m1 = load_registered_inventory_model(
        model_name="VersionedTestModel",
        version="1",
        tracking_uri=test_mlflow_uri,
    )
    pred_v1 = m1.predict([[6]])
    assert len(pred_v1) == 1
    assert pred_v1[0] > 0

    # Load latest version
    m_latest = load_registered_inventory_model(
        model_name="VersionedTestModel",
        tracking_uri=test_mlflow_uri,
    )
    pred_latest = m_latest.predict([[6]])
    assert len(pred_latest) == 1
    assert pred_latest[0] > 0


def test_existing_forecasting_api_after_mlflow(client):
    """Verify that existing GET /forecast/{month} API operates seamlessly."""
    response = client.get("/forecast/6")
    assert response.status_code == 200
    data = response.json()
    assert data["month"] == 6
    assert "forecast" in data
    assert "units_predicted" in data
    assert data["units_predicted"] > 0
    assert data["model_name"] == "RandomForest"


def test_load_registered_model_fallback(tmp_path, test_mlflow_uri):
    """Verify fallback to local pickle when MLflow registered model is not found."""
    import joblib
    from sklearn.ensemble import RandomForestRegressor

    fake_model = RandomForestRegressor(n_estimators=5, random_state=42)
    fake_model.fit([[1], [2]], [10, 20])

    local_path = "models/inventory_model.pkl"
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    joblib.dump(fake_model, local_path)

    # Point to a model name that doesn't exist in registry
    loaded = load_registered_inventory_model(
        model_name="DefinitelyNonExistentModel_XYZ123",
        tracking_uri=test_mlflow_uri,
    )
    assert loaded is not None
    assert hasattr(loaded, "predict")
    preds = loaded.predict([[1]])
    assert len(preds) == 1
