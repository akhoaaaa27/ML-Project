"""Server-owned configuration for trusted runtime inputs."""

from dataclasses import dataclass, field
from enum import StrEnum
import os
import re

from scripts.inference.common import MODEL_DIR, ROOT
from scripts.multisource.acquire import LOCAL
from scripts.multisource.forecast_examples import FIRST, UPDATE

PRIVATE = LOCAL / "phase857"
FRONTEND = ROOT / "web" / "xpecta"
PREPARED = PRIVATE / "frontend"
REAL_VERSION = "phase853_v3_20261122"
REAL_SHA256 = "110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e"
MODEL_SHA256 = "0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69"
MODEL_METADATA_SHA256 = "6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c"
DEMO_CLOCKS = {"initial": FIRST, "updated": UPDATE, "same-features": UPDATE, "incomplete": UPDATE}
APP_VERSION = "8.5.7"


class Mode(StrEnum):
    REAL_RESEARCH = "REAL_RESEARCH"
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    HISTORICAL_REFERENCE = "HISTORICAL_REFERENCE"


@dataclass(frozen=True)
class Settings:
    mode: Mode = Mode.REAL_RESEARCH
    snapshot_version: str = REAL_VERSION
    demo_name: str = "defense"
    operator_token: str = field(default="", repr=False)
    origins: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.mode, Mode):
            raise ValueError("Choose a supported XPECTA mode")
        allowed = DEMO_CLOCKS if self.mode == Mode.SYNTHETIC_DEMO else (REAL_VERSION,)
        if self.snapshot_version not in allowed:
            raise ValueError("Snapshot ID is outside the server allowlist")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", self.demo_name):
            raise ValueError("Invalid local demo name")
        if self.operator_token and (len(self.operator_token) < 24 or self.mode == Mode.HISTORICAL_REFERENCE):
            raise ValueError("Use a strong operator token in a forecasting mode")
        if any(not re.fullmatch(r"http://(?:localhost|127\.0\.0\.1)(?::[1-9][0-9]{0,4})?", origin)
               for origin in self.origins):
            raise ValueError("Development origins must be explicit loopback HTTP origins")

    @property
    def demo_root(self):
        root = (PRIVATE / "demos" / self.demo_name).absolute()
        if root.resolve() != root:
            raise ValueError("Use a direct local demo directory")
        return root

    @classmethod
    def from_env(cls):
        mode = Mode(os.getenv("XPECTA_MODE", Mode.REAL_RESEARCH))
        default_version = "updated" if mode == Mode.SYNTHETIC_DEMO else REAL_VERSION
        return cls(
            mode=mode,
            snapshot_version=os.getenv("XPECTA_SNAPSHOT", default_version),
            demo_name=os.getenv("XPECTA_DEMO_NAME", "defense"),
            operator_token=os.getenv("XPECTA_OPERATOR_TOKEN", ""),
            origins=tuple(s.strip() for s in os.getenv("XPECTA_DEV_ORIGINS", "").split(",") if s.strip()),
        )
