import hashlib
import hmac
import re
import secrets

from agent.database import get_connection


# ============================================================
# AUTHENTICATION SETTINGS
# ============================================================

MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 30

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

MIN_FULL_NAME_LENGTH = 2
MAX_FULL_NAME_LENGTH = 100

PBKDF2_ITERATIONS = 310_000

PASSWORD_HASH_ALGORITHM = "sha256"

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_]*$"
)

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

DEMO_USERNAME = "demo"


# ============================================================
# TEXT NORMALISATION
# ============================================================

def normalize_username(username):
    """
    Normalize usernames for consistent storage and lookup.
    """

    if not isinstance(
        username,
        str
    ):
        return ""

    return username.strip()


def normalize_full_name(full_name):
    """
    Normalize a user's display name.
    """

    if not isinstance(
        full_name,
        str
    ):
        return ""

    return " ".join(
        full_name.strip().split()
    )


def normalize_email(email):
    """
    Normalize optional email addresses.
    """

    if email is None:
        return None

    if not isinstance(
        email,
        str
    ):
        return None

    email = email.strip()

    if not email:
        return None

    return email.lower()


# ============================================================
# USERNAME VALIDATION
# ============================================================

def validate_username(username):
    """
    Validate username format and length.
    """

    username = normalize_username(
        username
    )

    if not username:

        return (
            False,
            "Username cannot be empty."
        )

    if len(username) < MIN_USERNAME_LENGTH:

        return (
            False,
            (
                f"Username must be at least "
                f"{MIN_USERNAME_LENGTH} characters."
            )
        )

    if len(username) > MAX_USERNAME_LENGTH:

        return (
            False,
            (
                f"Username cannot exceed "
                f"{MAX_USERNAME_LENGTH} characters."
            )
        )

    if not USERNAME_PATTERN.fullmatch(
        username
    ):

        return (
            False,
            (
                "Username may only contain letters, "
                "numbers and underscores."
            )
        )

    return True, ""


# ============================================================
# PASSWORD VALIDATION
# ============================================================

def validate_password(password):
    """
    Validate password length.

    The actual password is never logged, stored in state,
    or returned by this module.
    """

    if not isinstance(
        password,
        str
    ):

        return (
            False,
            "Password must be text."
        )

    if len(password) < MIN_PASSWORD_LENGTH:

        return (
            False,
            (
                f"Password must be at least "
                f"{MIN_PASSWORD_LENGTH} characters."
            )
        )

    if len(password) > MAX_PASSWORD_LENGTH:

        return (
            False,
            (
                f"Password cannot exceed "
                f"{MAX_PASSWORD_LENGTH} characters."
            )
        )

    return True, ""


# ============================================================
# FULL NAME VALIDATION
# ============================================================

def validate_full_name(full_name):
    """
    Validate full name.
    """

    full_name = normalize_full_name(
        full_name
    )

    if not full_name:

        return (
            False,
            "Full name cannot be empty."
        )

    if len(full_name) < MIN_FULL_NAME_LENGTH:

        return (
            False,
            (
                f"Full name must be at least "
                f"{MIN_FULL_NAME_LENGTH} characters."
            )
        )

    if len(full_name) > MAX_FULL_NAME_LENGTH:

        return (
            False,
            (
                f"Full name cannot exceed "
                f"{MAX_FULL_NAME_LENGTH} characters."
            )
        )

    return True, ""


# ============================================================
# EMAIL VALIDATION
# ============================================================

def validate_email(email):
    """
    Validate an optional email address.
    """

    if email is None:

        return True, ""

    email = normalize_email(
        email
    )

    if email is None:

        return True, ""

    if len(email) > 254:

        return (
            False,
            "Email address is too long."
        )

    if not EMAIL_PATTERN.fullmatch(
        email
    ):

        return (
            False,
            "Please enter a valid email address."
        )

    return True, ""


# ============================================================
# PASSWORD HASHING
# ============================================================

def hash_password(password):
    """
    Hash a password using PBKDF2-HMAC-SHA256 with a unique
    random salt.

    Stored format:

        pbkdf2_sha256$iterations$salt$hash
    """

    if not isinstance(
        password,
        str
    ):

        raise TypeError(
            "Password must be a string."
        )

    salt = secrets.token_bytes(
        32
    )

    password_hash = hashlib.pbkdf2_hmac(

        PASSWORD_HASH_ALGORITHM,

        password.encode(
            "utf-8"
        ),

        salt,

        PBKDF2_ITERATIONS

    )

    return (

        "pbkdf2_sha256$"
        f"{PBKDF2_ITERATIONS}$"
        f"{salt.hex()}$"
        f"{password_hash.hex()}"

    )


# ============================================================
# PASSWORD VERIFICATION
# ============================================================

def verify_password(
    password,
    stored_hash
):
    """
    Verify a password against a stored PBKDF2 hash.
    """

    if not isinstance(
        password,
        str
    ):

        return False

    if not isinstance(
        stored_hash,
        str
    ):

        return False

    parts = stored_hash.split(
        "$"
    )

    if len(parts) != 4:

        return False

    algorithm = parts[0]
    iterations_text = parts[1]
    salt_hex = parts[2]
    stored_hash_hex = parts[3]

    if algorithm != "pbkdf2_sha256":

        return False

    try:

        iterations = int(
            iterations_text
        )

        if iterations <= 0:

            return False

        salt = bytes.fromhex(
            salt_hex
        )

        expected_hash = bytes.fromhex(
            stored_hash_hex
        )

    except (
        ValueError,
        TypeError
    ):

        return False

    calculated_hash = hashlib.pbkdf2_hmac(

        PASSWORD_HASH_ALGORITHM,

        password.encode(
            "utf-8"
        ),

        salt,

        iterations

    )

    return hmac.compare_digest(

        calculated_hash,

        expected_hash

    )


# ============================================================
# SAFE USER OBJECT
# ============================================================

def build_safe_user(row):
    """
    Convert a database row into safe user information.

    IMPORTANT:
    password_hash is never returned.
    """

    if row is None:

        return None

    return {
        "id":
            row["id"],

        "username":
            row["username"],

        "full_name":
            row["full_name"],

        "email":
            row["email"],

        "status":
            row["status"],

        "role":
            row["role"],

        "created_at":
            row["created_at"]

    }


# ============================================================
# REGISTER USER
# ============================================================

def register_user(
    username,
    password,
    full_name,
    email=None
):
    """
    Register a new active library user.
    """

    username = normalize_username(
        username
    )

    full_name = normalize_full_name(
        full_name
    )

    email = normalize_email(
        email
    )

    # --------------------------------------------------------
    # Validate username
    # --------------------------------------------------------

    valid, message = validate_username(
        username
    )

    if not valid:

        return {
            "success": False,
            "message": message
        }

    # --------------------------------------------------------
    # Validate password
    # --------------------------------------------------------

    valid, message = validate_password(
        password
    )

    if not valid:

        return {
            "success": False,
            "message": message
        }

    # --------------------------------------------------------
    # Validate full name
    # --------------------------------------------------------

    valid, message = validate_full_name(
        full_name
    )

    if not valid:

        return {
            "success": False,
            "message": message
        }

    # --------------------------------------------------------
    # Validate email
    # --------------------------------------------------------

    valid, message = validate_email(
        email
    )

    if not valid:

        return {
            "success": False,
            "message": message
        }

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Check username
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE LOWER(username) = LOWER(?)
            LIMIT 1
            """,
            (
                username,
            )
        )

        if cursor.fetchone() is not None:

            return {
                "success": False,
                "message":
                    "Username is already registered."
            }

        # ----------------------------------------------------
        # Check email
        # ----------------------------------------------------

        if email:

            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE LOWER(email) = LOWER(?)
                LIMIT 1
                """,
                (
                    email,
                )
            )

            if cursor.fetchone() is not None:

                return {
                    "success": False,
                    "message":
                        "Email address is already registered."
                }

        # ----------------------------------------------------
        # Hash password
        # ----------------------------------------------------

        password_hash = hash_password(
            password
        )

        # ----------------------------------------------------
        # Insert user
        # ----------------------------------------------------

        cursor.execute(
            """
            INSERT INTO users
            (
                username,
                password_hash,
                full_name,
                email,
                status
            )
            VALUES (?, ?, ?, ?, 'active')
            """,
            (
                username,
                password_hash,
                full_name,
                email,
            )
        )

        user_id = cursor.lastrowid

        connection.commit()

        return {

            "success":
                True,

            "message":
                "Account created successfully.",

            "user": {

                "id":
                    user_id,

                "username":
                    username,

                "full_name":
                    full_name,

                "email":
                    email,

                "status":
                    "active",

                "role":
                    "member"

            }

        }

    except Exception:

        connection.rollback()

        return {

            "success":
                False,

            "message":
                "Account registration failed."

        }

    finally:

        connection.close()


# ============================================================
# AUTHENTICATE USER
# ============================================================

def authenticate_user(
    username,
    password
):
    """
    Authenticate a user.

    The returned object never contains password_hash.
    """

    username = normalize_username(
        username
    )

    if not username:

        return {

            "success":
                False,

            "message":
                "Invalid username or password."

        }

    if not isinstance(
        password,
        str
    ):

        return {

            "success":
                False,

            "message":
                "Invalid username or password."

        }

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                username,
                password_hash,
                full_name,
                email,
                status,
                role,
                created_at

            FROM users

            WHERE LOWER(username) = LOWER(?)

            LIMIT 1
            """,
            (
                username,
            )
        )

        row = cursor.fetchone()

        # ----------------------------------------------------
        # Same message whether the username exists or not.
        # ----------------------------------------------------

        if row is None:

            return {

                "success":
                    False,

                "message":
                    "Invalid username or password."

            }

        # ----------------------------------------------------
        # Account status
        # ----------------------------------------------------

        if row["status"] != "active":

            return {

                "success":
                    False,

                "message":
                    "This account is currently inactive."

            }

        # ----------------------------------------------------
        # Verify password
        # ----------------------------------------------------

        if not verify_password(
            password,
            row["password_hash"]
        ):

            return {

                "success":
                    False,

                "message":
                    "Invalid username or password."

            }

        return {

            "success":
                True,

            "message":
                "Login successful.",

            "user":
                build_safe_user(row)

        }

    finally:

        connection.close()


# ============================================================
# GET USER BY ID
# ============================================================

def get_user_by_id(
    user_id
):
    """
    Retrieve safe user information.
    """

    try:

        user_id = int(
            user_id
        )

    except (
        TypeError,
        ValueError
    ):

        return None

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                username,
                full_name,
                email,
                status,
                role,
                created_at

            FROM users

            WHERE id = ?

            LIMIT 1
            """,
            (
                user_id,
            )
        )

        row = cursor.fetchone()

        return build_safe_user(
            row
        )

    finally:

        connection.close()


# ============================================================
# GET USER BY USERNAME
# ============================================================

def get_user_by_username(
    username
):
    """
    Retrieve safe user information.
    """

    username = normalize_username(
        username
    )

    if not username:

        return None

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                username,
                full_name,
                email,
                status,
                role,
                created_at

            FROM users

            WHERE LOWER(username) = LOWER(?)

            LIMIT 1
            """,
            (
                username,
            )
        )

        row = cursor.fetchone()

        return build_safe_user(
            row
        )

    finally:

        connection.close()


# ============================================================
# CHECK ACTIVE USER
# ============================================================

def is_user_active(
    user_id
):
    """
    Return True when the account exists and is active.
    """

    user = get_user_by_id(
        user_id
    )

    if user is None:

        return False

    return user["status"] == "active"


# ============================================================
# GET USER ROLE
# ============================================================

def get_user_role(
    user_id
):
    """
    Return the role of an active user, or None.
    """

    user = get_user_by_id(
        user_id
    )

    if user is None:

        return None

    if user["status"] != "active":

        return None

    return user.get(
        "role",
        "member"
    )


# ============================================================
# DEMO LOGIN
# ============================================================

def login_demo_user():
    """
    Select the development demo account.

    This is intended for local testing before a real user
    chooses Login.
    """

    user = get_user_by_username(
        DEMO_USERNAME
    )

    if user is None:

        return {

            "success":
                False,

            "message":
                "Demo account not found."

        }

    if user["status"] != "active":

        return {

            "success":
                False,

            "message":
                "Demo account is inactive."

        }

    return {

        "success":
            True,

        "message":
            "Demo account selected.",

        "user":
            user

    }