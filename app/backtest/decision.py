from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any

@dataclass(frozen=True)
class Decision:
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float              # 0.0 → 1.0
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    metadata: Optional[Dict[str, Any]] = None
