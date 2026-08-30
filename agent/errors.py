# ============================================================
# APPLICATION ERROR TYPES
# ============================================================


class LibraryAppError(Exception):
    """
    Base application-level error.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):
        super().__init__(message)

        self.message = message

        self.user_message = (
            user_message
            if user_message
            else message
        )


# ============================================================
# VALIDATION ERROR
# ============================================================

class ValidationError(LibraryAppError):
    """
    Invalid or incomplete input.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):

        super().__init__(
            message,
            user_message
            or
            "The information provided is invalid."
        )


# ============================================================
# AUTHENTICATION ERROR
# ============================================================

class AuthenticationError(LibraryAppError):
    """
    Authentication failure.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):

        super().__init__(
            message,
            user_message
            or
            "Authentication failed."
        )


# ============================================================
# AUTHORIZATION ERROR
# ============================================================

class AuthorizationError(LibraryAppError):
    """
    User is not allowed to perform an operation.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):

        super().__init__(
            message,
            user_message
            or
            "You are not allowed to perform this operation."
        )


# ============================================================
# DATABASE ERROR
# ============================================================

class DatabaseError(LibraryAppError):
    """
    Database operation failure.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):

        super().__init__(
            message,
            user_message
            or
            (
                "The library database could not complete "
                "the requested operation."
            )
        )


# ============================================================
# TOOL ERROR
# ============================================================

class ToolError(LibraryAppError):
    """
    Library tool execution failure.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):

        super().__init__(
            message,
            user_message
            or
            (
                "The library operation could not be completed."
            )
        )


# ============================================================
# AI SERVICE ERROR
# ============================================================

class AIServiceError(LibraryAppError):
    """
    AI service/API failure.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):

        super().__init__(
            message,
            user_message
            or
            (
                "The AI service is temporarily unavailable. "
                "Please try again."
            )
        )


# ============================================================
# BUSINESS RULE ERROR
# ============================================================

class BusinessRuleError(LibraryAppError):
    """
    Library business-rule violation.
    """

    def __init__(
        self,
        message,
        user_message=None
    ):

        super().__init__(
            message,
            user_message
            or
            "The requested library operation cannot be performed."
        )


# ============================================================
# USER-FACING ERROR MESSAGE
# ============================================================

def get_user_error_message(error):
    """
    Return a safe message suitable for the user interface.
    """

    if isinstance(
        error,
        LibraryAppError
    ):

        return error.user_message

    return (
        "The application encountered an unexpected error."
    )