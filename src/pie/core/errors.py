class PieError(Exception):
    """Expected user-facing PIE error."""


class ProjectNotInitializedError(PieError):
    pass

