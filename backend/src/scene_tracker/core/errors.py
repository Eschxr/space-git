class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **details):
        self.code = code
        self.message = message
        self.status = status
        self.details = details
        super().__init__(message)
