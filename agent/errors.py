# ============================================================
# USER-FACING ERROR MESSAGE
# ============================================================

def get_user_error_message(error):
    """
    Return a safe message suitable for the user interface.

    Internal exception details are intentionally not exposed
    to end users.
    """

    return (
        "The application encountered an unexpected error."
    )
