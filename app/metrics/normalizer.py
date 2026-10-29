# trading_backend\app\metrics\normalizer.py
import math

class MetricsNormalizer:
    def normalize(self, data):
        if isinstance(data, float):
            if math.isnan(data) or math.isinf(data):
                return None
            return float(data)

        if isinstance(data, dict):
            return {k: self.normalize(v) for k, v in data.items()}

        if isinstance(data, list):
            return [self.normalize(v) for v in data]

        return data
