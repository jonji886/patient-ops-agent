from fastapi.responses import JSONResponse


def api_error(status: int, code: str, message: str, retryable: bool = False, outcome: str = "NOT_EXECUTED") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "outcome": outcome,
                "correlation_id": None,
            }
        },
    )
