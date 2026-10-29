from datetime import datetime

class SignalState:
    def __init__(self):
        self.last_signal = None
        self.last_signal_time = None

class SignalStateManager:
    def __init__(self):
        self._states = {}

    def should_emit(self, symbol: str, signal: str, candle_time: datetime) -> bool:
        state = self._states.get(symbol)

        if not state:
            self._states[symbol] = SignalState()
            self._states[symbol].last_signal = signal
            self._states[symbol].last_signal_time = candle_time
            return True

        if state.last_signal != signal:
            state.last_signal = signal
            state.last_signal_time = candle_time
            return True

        return False
