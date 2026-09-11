"""Dataset adapter registry for synthetic and paper datasets."""

from __future__ import annotations

from raven_mcs.data.base import DatasetAdapter
from raven_mcs.data.cityscanner import CityScannerNYCPM25Adapter
from raven_mcs.data.sensorscope import SensorScopeAdapter
from raven_mcs.data.synthetic import SyntheticDatasetAdapter
from raven_mcs.data.tdrive import TDriveSpeedAdapter
from raven_mcs.data.traffic import TrafficAdapter
from raven_mcs.data.uair import UAirAdapter


class AdapterUnavailableError(NotImplementedError):
    pass


_ADAPTERS: dict[str, type[DatasetAdapter]] = {
    "synthetic": SyntheticDatasetAdapter,
    "sensorscope": SensorScopeAdapter,
    "uair": UAirAdapter,
    "u_air": UAirAdapter,
    "traffic": TrafficAdapter,
    "traffic_volume": TrafficAdapter,
    "tdrive": TDriveSpeedAdapter,
    "tdrive_speed": TDriveSpeedAdapter,
    "cityscanner_nyc_pm25": CityScannerNYCPM25Adapter,
    "cityscanner": CityScannerNYCPM25Adapter,
}


def get_dataset_adapter(name: str) -> DatasetAdapter:
    normalized = name.strip().lower().replace("-", "_")
    try:
        return _ADAPTERS[normalized]()
    except KeyError as exc:
        raise KeyError(f"Unknown dataset adapter: {name}") from exc
