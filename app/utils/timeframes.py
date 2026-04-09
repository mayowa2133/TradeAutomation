TIMEFRAME_TO_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
}


def validate_timeframe(timeframe: str) -> str:
    if timeframe not in TIMEFRAME_TO_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return timeframe


def timeframe_to_minutes(timeframe: str) -> int:
    return TIMEFRAME_TO_MINUTES[validate_timeframe(timeframe)]


def timeframe_to_pandas_freq(timeframe: str) -> str:
    return f"{timeframe_to_minutes(timeframe)}min"
