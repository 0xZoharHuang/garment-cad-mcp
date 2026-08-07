class GarmentCadError(RuntimeError):
    """Base domain error."""


class ProjectNotFoundError(GarmentCadError):
    pass


class ProjectLockedError(GarmentCadError):
    pass


class StaleRevisionError(GarmentCadError):
    pass


class ChangeSetNotFoundError(GarmentCadError):
    pass


class CommandBackendUnavailable(GarmentCadError):
    pass
