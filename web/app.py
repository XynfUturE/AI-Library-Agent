from pathlib import Path
import json

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)

from fastapi.responses import (
    HTMLResponse,
    StreamingResponse,
)

from fastapi.staticfiles import StaticFiles

from fastapi.templating import Jinja2Templates


from agent import tools as library_tools

from agent import catalog as catalog_service

from agent.auth import (
    authenticate_user,
    get_user_by_id,
    login_demo_user,
    register_user,
)

from agent.core import LibraryAgent

from agent.database import get_connection


from web.models import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    ChatRequest,
    ChatResponse,
    SessionCheckResponse,
    ShelfSummaryResponse,
    ShelfItemsResponse,
    CatalogResponse,
    CatalogCategoriesResponse,
    CatalogBooksResponse,
    AdminBookPayload,
    AdminBookUpdatePayload,
    AdminBookResult,
    AdminBookImportRequest,
    AdminBookImportResult,
)

from web.session import (
    create_session,
    get_session,
    set_agent,
    delete_session,
)


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="AI Library Agent",
    version="1.1.0",
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(
    __file__
).resolve().parent


TEMPLATES_DIR = (
    BASE_DIR /
    "templates"
)


STATIC_DIR = (
    BASE_DIR /
    "static"
)


# ============================================================
# TEMPLATE ENGINE
# ============================================================

templates = Jinja2Templates(
    directory=str(
        TEMPLATES_DIR
    )
)


# ============================================================
# STATIC FILES
# ============================================================

class CacheControlledStaticFiles(StaticFiles):
    """
    Serve static assets with a sane Cache-Control policy:

    * Versioned URLs (?v=...) — the entry CSS/JS and the favicon —
      are unique per release, so they may be cached for a long time.
    * Un-versioned URLs (the ES-module sub-imports) are only cached
      briefly; Starlette still sends ETag / Last-Modified, so the
      browser revalidates them cheaply with a 304 after that window.
    """
    VERSIONED_MAX_AGE = 60 * 60 * 24 * 365
    DEFAULT_MAX_AGE = 60

    async def get_response(self, path, scope):

        response = await super().get_response(path, scope)

        if response.status_code == 200:

            if scope.get("query_string"):

                max_age = self.VERSIONED_MAX_AGE

            else:

                max_age = self.DEFAULT_MAX_AGE

            response.headers.setdefault(
                "Cache-Control",
                f"public, max-age={max_age}",
            )

        return response


app.mount(
    "/static",
    CacheControlledStaticFiles(
        directory=str(
            STATIC_DIR
        )
    ),
    name="static",
)


def _asset_version():
    """
    Self-refreshing cache-busting stamp for entry assets: the newest
    file mtime under /static. Touching any front-end file produces a
    fresh query string (?v=...) on the next page load.
    """
    latest = 0.0

    for path in STATIC_DIR.rglob("*"):

        if not path.is_file():

            continue

        try:

            latest = max(
                latest,
                path.stat().st_mtime,
            )

        except OSError:

            continue

    return str(
        int(latest)
    )


# ============================================================
# HOME
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
def home(
    request: Request,
):

    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "asset_version": _asset_version(),
        },
    )

    # Never cache the HTML shell: it carries the versioned asset
    # URLs (?v=...) that invalidate long-lived static caches.
    response.headers["Cache-Control"] = "no-cache"

    return response


# ============================================================
# CREATE AUTHENTICATED SESSION
# ============================================================

def create_authenticated_session(
    user,
    success_message="Login successful.",
):

    if not isinstance(
        user,
        dict,
    ):

        raise HTTPException(
            status_code=500,
            detail=(
                "User account information "
                "could not be loaded."
            ),
        )


    user_id = user.get(
        "id"
    )


    if user_id is None:

        raise HTTPException(
            status_code=500,
            detail=(
                "User account information "
                "is incomplete."
            ),
        )


    try:

        user_id = int(
            user_id
        )

    except (
        TypeError,
        ValueError,
    ):

        raise HTTPException(
            status_code=500,
            detail=(
                "User account information "
                "is invalid."
            ),
        )


    # --------------------------------------------------------
    # Create Session
    # --------------------------------------------------------

    session_id = create_session(
        user_id
    )


    # --------------------------------------------------------
    # The dedicated Agent is created lazily on the first chat
    # request, so idle sessions do not hold an OpenAI client.
    # --------------------------------------------------------


    return LoginResponse(
        success=True,
        message=success_message,
        user_id=user_id,
        username=user.get(
            "username"
        ),
        role=user.get(
            "role"
        ),
        session_id=session_id,
    )


# ============================================================
# AGENT (LAZY CREATION ON FIRST CHAT)
# ============================================================

def ensure_agent(
    session: dict,
    session_id: str | None,
):
    """
    Return the Agent attached to a session, creating it on first use.
    """

    agent = session.get(
        "agent"
    )

    if agent is not None:

        return agent


    try:

        agent = LibraryAgent(
            user_id=session["user_id"]
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail=(
                "The AI agent could not "
                "be initialized."
            ),
        )


    if not set_agent(
        session_id,
        agent,
    ):

        raise HTTPException(
            status_code=500,
            detail=(
                "The user session could "
                "not be initialized."
            ),
        )

    return agent


# ============================================================
# NORMAL LOGIN
# ============================================================

@app.post(
    "/api/login",
    response_model=LoginResponse,
)
def login(
    request: LoginRequest,
):

    result = authenticate_user(
        request.username,
        request.password,
    )


    if not isinstance(
        result,
        dict,
    ):

        raise HTTPException(
            status_code=500,
            detail="Authentication failed.",
        )


    if result.get(
        "success"
    ) is not True:

        return LoginResponse(
            success=False,
            message=result.get(
                "message",
                "Login failed.",
            ),
        )


    return create_authenticated_session(
        result.get(
            "user",
            {},
        )
    )


# ============================================================
# DEMO LOGIN
# ============================================================

@app.post(
    "/api/demo-login",
    response_model=LoginResponse,
)
def demo_login():

    result = login_demo_user()


    if not isinstance(
        result,
        dict,
    ):

        raise HTTPException(
            status_code=500,
            detail=(
                "The demo account could "
                "not be loaded."
            ),
        )


    if result.get(
        "success"
    ) is not True:

        return LoginResponse(
            success=False,
            message=result.get(
                "message",
                "Demo login failed.",
            ),
        )


    return create_authenticated_session(
        result.get(
            "user",
            {},
        ),
        success_message=(
            "Demo account activated."
        ),
    )


# ============================================================
# REGISTER
# ============================================================

@app.post(
    "/api/register",
    response_model=LoginResponse,
)
def register(
    request: RegisterRequest,
):

    # --------------------------------------------------------
    # The current Auth layer still expects full_name.
    #
    # The Web UI does not ask the user for it.
    # We safely use the username as the initial display name.
    # --------------------------------------------------------

    result = register_user(
        username=request.username,
        password=request.password,
        full_name=request.username,
        email=request.email,
    )


    if not isinstance(
        result,
        dict,
    ):

        raise HTTPException(
            status_code=500,
            detail="Registration failed.",
        )


    if result.get(
        "success"
    ) is not True:

        return LoginResponse(
            success=False,
            message=result.get(
                "message",
                "Registration failed.",
            ),
        )


    return create_authenticated_session(
        result.get(
            "user",
            {},
        ),
        success_message=(
            "Account created successfully."
        ),
    )


# ============================================================
# NORMAL CHAT
# ============================================================

@app.post(
    "/api/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
    x_session_id: str | None = Header(
        default=None
    ),
):

    session = get_session(
        x_session_id
    )


    if session is None:

        raise HTTPException(
            status_code=401,
            detail="Please log in first.",
        )


    agent = ensure_agent(
        session,
        x_session_id,
    )


    try:

        reply = agent.chat(
            request.message
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail=(
                "The AI service could not "
                "complete your request."
            ),
        )


    return ChatResponse(
        success=True,
        reply=reply,
    )


# ============================================================
# STREAMING CHAT
# ============================================================

@app.post(
    "/api/chat/stream",
)
def chat_stream(
    request: ChatRequest,
    x_session_id: str | None = Header(
        default=None
    ),
):

    session = get_session(
        x_session_id
    )


    if session is None:

        raise HTTPException(
            status_code=401,
            detail="Please log in first.",
        )


    agent = ensure_agent(
        session,
        x_session_id,
    )


    def event_generator():

        try:

            for event in agent.chat_stream(
                request.message
            ):

                yield (
                    "data: "
                    +
                    json.dumps(
                        event,
                        ensure_ascii=False,
                    )
                    +
                    "\n\n"
                )

        except ValueError as error:

            yield (
                "data: "
                +
                json.dumps(
                    {
                        "type": "error",
                        "message": str(error),
                    },
                    ensure_ascii=False,
                )
                +
                "\n\n"
            )

        except Exception:

            yield (
                "data: "
                +
                json.dumps(
                    {
                        "type": "error",
                        "message": (
                            "The AI service could "
                            "not complete your request."
                        ),
                    },
                    ensure_ascii=False,
                )
                +
                "\n\n"
            )


    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# LOGOUT
# ============================================================

@app.post(
    "/api/logout",
)
def logout(
    x_session_id: str | None = Header(
        default=None
    ),
):

    delete_session(
        x_session_id
    )


    return {
        "success": True,
        "message": (
            "Logged out successfully."
        ),
    }


# ============================================================
# SESSION GUARD (SHARED BY READ-ONLY ENDPOINTS)
# ============================================================

def require_session(
    x_session_id: str | None,
) -> dict:

    session = get_session(
        x_session_id
    )

    if session is None:

        raise HTTPException(
            status_code=401,
            detail="Please log in first.",
        )

    return session


def library_data_or_error(
    data,
    fallback_message,
):

    # --------------------------------------------------------
    # Library tool helpers return a list (or payload dictionary)
    # on success and a safe error dictionary on failure.
    # --------------------------------------------------------

    if isinstance(
        data,
        dict,
    ) and data.get(
        "success"
    ) is False:

        raise HTTPException(
            status_code=500,
            detail=data.get(
                "message",
                fallback_message,
            ),
        )

    return data


def extract_unpaid_fines(
    user_id,
):

    # --------------------------------------------------------
    # get_unpaid_fines wraps its list in a payload dictionary
    # with a pre-computed total.
    # --------------------------------------------------------

    payload = library_data_or_error(
        library_tools.get_unpaid_fines(
            user_id
        ),
        "Your unpaid fines could "
        "not be retrieved.",
    )

    if isinstance(
        payload,
        dict,
    ) and "fines" in payload:

        return payload.get(
            "fines",
            [],
        )

    return payload


# ============================================================
# SESSION CHECK (RESTORE LOGIN AFTER PAGE REFRESH)
# ============================================================

@app.get(
    "/api/session/check",
    response_model=SessionCheckResponse,
)
def session_check(
    x_session_id: str | None = Header(
        default=None
    ),
):

    session = require_session(
        x_session_id
    )

    user = get_user_by_id(
        session.get(
            "user_id"
        )
    )

    if user is None:

        raise HTTPException(
            status_code=401,
            detail="Please log in first.",
        )

    return SessionCheckResponse(
        success=True,
        user_id=user["id"],
        username=user["username"],
        full_name=user.get(
            "full_name"
        ),
        role=user.get(
            "role"
        ),
    )


# ============================================================
# SHELF SUMMARY
# ============================================================

@app.get(
    "/api/shelf/summary",
    response_model=ShelfSummaryResponse,
)
def shelf_summary(
    x_session_id: str | None = Header(
        default=None
    ),
):

    session = require_session(
        x_session_id
    )

    user_id = session.get(
        "user_id"
    )

    loans = library_data_or_error(
        library_tools.get_current_borrowed_books(
            user_id
        ),
        "Your current borrowed books "
        "could not be retrieved.",
    )

    fines = extract_unpaid_fines(
        user_id
    )

    history = library_data_or_error(
        library_tools.get_borrow_history(
            user_id
        ),
        "Your borrowing history could "
        "not be retrieved.",
    )

    overdue_count = sum(
        1
        for loan in loans
        if loan.get(
            "is_overdue"
        )
    )

    unpaid_total = round(
        sum(
            fine.get(
                "fine_amount",
                0,
            )
            for fine in fines
        ),
        2,
    )

    return ShelfSummaryResponse(
        success=True,
        active_loans=len(
            loans
        ),
        overdue_count=overdue_count,
        unpaid_fines_total=unpaid_total,
        total_borrowed=len(
            history
        ),
    )


# ============================================================
# SHELF: ACTIVE LOANS
# ============================================================

@app.get(
    "/api/shelf/loans",
    response_model=ShelfItemsResponse,
)
def shelf_loans(
    x_session_id: str | None = Header(
        default=None
    ),
):

    session = require_session(
        x_session_id
    )

    loans = library_data_or_error(
        library_tools.get_current_borrowed_books(
            session.get(
                "user_id"
            )
        ),
        "Your current borrowed books "
        "could not be retrieved.",
    )

    return ShelfItemsResponse(
        success=True,
        items=loans,
    )


# ============================================================
# SHELF: UNPAID FINES
# ============================================================

@app.get(
    "/api/shelf/fines",
    response_model=ShelfItemsResponse,
)
def shelf_fines(
    x_session_id: str | None = Header(
        default=None
    ),
):

    session = require_session(
        x_session_id
    )

    fines = extract_unpaid_fines(
        session.get(
            "user_id"
        )
    )

    return ShelfItemsResponse(
        success=True,
        items=fines,
    )


# ============================================================
# SHELF: BORROW HISTORY
# ============================================================

@app.get(
    "/api/shelf/history",
    response_model=ShelfItemsResponse,
)
def shelf_history(
    x_session_id: str | None = Header(
        default=None
    ),
):

    session = require_session(
        x_session_id
    )

    history = library_data_or_error(
        library_tools.get_borrow_history(
            session.get(
                "user_id"
            )
        ),
        "Your borrowing history could "
        "not be retrieved.",
    )

    return ShelfItemsResponse(
        success=True,
        items=history,
    )


# ============================================================
# BOOK CATALOG (READ-ONLY)
# ============================================================

def fetch_book_catalog(
    keyword=None,
):

    connection = None

    try:

        connection = get_connection()

        cursor = connection.cursor()

        if keyword:

            cursor.execute(
                """
                SELECT
                    id,
                    title,
                    author,
                    available
                FROM books
                WHERE title LIKE ?
                    OR author LIKE ?
                ORDER BY title
                """,
                (
                    f"%{keyword}%",
                    f"%{keyword}%",
                ),
            )

        else:

            cursor.execute(
                """
                SELECT
                    id,
                    title,
                    author,
                    available
                FROM books
                ORDER BY title
                """
            )

        rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "title": row["title"],
                "author": row["author"],
                "available": bool(
                    row["available"]
                ),
            }
            for row in rows
        ]

    finally:

        if connection is not None:

            connection.close()


@app.get(
    "/api/books",
    response_model=CatalogResponse,
)
def book_catalog(
    q: str | None = Query(
        default=None
    ),
    x_session_id: str | None = Header(
        default=None
    ),
):

    require_session(
        x_session_id
    )

    keyword = (
        q.strip()
        if isinstance(
            q,
            str,
        )
        else None
    )

    items = fetch_book_catalog(
        keyword=keyword or None,
    )

    return CatalogResponse(
        success=True,
        items=items,
        query=keyword,
    )


# ============================================================
# CATALOG GUARDS
# ============================================================

def require_admin(
    x_session_id: str | None,
) -> dict:
    """
    Require an authenticated administrator session.

    Raises 403 for every non-admin (even active members), so the
    write endpoints stay hidden from regular library users.
    """

    session = require_session(
        x_session_id
    )

    user = get_user_by_id(
        session.get(
            "user_id"
        )
    )

    if (
        user is None
        or user.get("role") != "admin"
    ):

        raise HTTPException(
            status_code=403,
            detail=(
                "Administrator access is required "
                "to manage the catalog."
            ),
        )

    return session


def admin_result_or_error(
    result,
    fallback_message,
):

    # --------------------------------------------------------
    # Catalog service write operations return a payload
    # dictionary on success and a safe error dictionary
    # (success False + error_type) on failure. Validation
    # problems map to 400; database problems map to 500.
    # --------------------------------------------------------

    if isinstance(
        result,
        dict,
    ) and result.get(
        "success"
    ) is False:

        error_type = result.get(
            "error_type"
        )

        raise HTTPException(
            status_code=(
                400
                if error_type == "ValidationError"
                else 500
            ),
            detail=result.get(
                "message",
                fallback_message,
            ),
        )

    return result


# ============================================================
# CATALOG CATEGORY TREE
# ============================================================

@app.get(
    "/api/catalog/categories",
    response_model=CatalogCategoriesResponse,
)
def catalog_categories(
    x_session_id: str | None = Header(
        default=None
    ),
):

    require_session(
        x_session_id
    )

    payload = catalog_service.get_catalog_categories()

    return library_data_or_error(
        payload,
        "The catalog categories could "
        "not be retrieved.",
    )


# ============================================================
# CATALOG BOOKS (EXTENDED QUERY)
# ============================================================

@app.get(
    "/api/catalog/books",
    response_model=CatalogBooksResponse,
)
def catalog_books(
    q: str | None = Query(
        default=None
    ),
    category_id: int | None = Query(
        default=None
    ),
    availability: str | None = Query(
        default=None
    ),
    x_session_id: str | None = Header(
        default=None
    ),
):

    require_session(
        x_session_id
    )

    items = catalog_service.query_catalog(
        keyword=q,
        category_id=category_id,
        availability=availability,
    )

    return CatalogBooksResponse(
        success=True,
        items=library_data_or_error(
            items,
            "The catalog could not "
            "be retrieved.",
        ),
    )


# ============================================================
# ADMIN: ADD A BOOK
# ============================================================

@app.post(
    "/api/admin/books",
    response_model=AdminBookResult,
)
def admin_add_book(
    request: AdminBookPayload,
    x_session_id: str | None = Header(
        default=None
    ),
):

    require_admin(
        x_session_id
    )

    result = admin_result_or_error(
        catalog_service.create_book(
            request.model_dump()
        ),
        "The book could not be added.",
    )

    return result


# ============================================================
# ADMIN: UPDATE A BOOK
# ============================================================

@app.put(
    "/api/admin/books/{book_id}",
    response_model=AdminBookResult,
)
def admin_update_book(
    book_id: int,
    request: AdminBookUpdatePayload,
    x_session_id: str | None = Header(
        default=None
    ),
):

    require_admin(
        x_session_id
    )

    result = admin_result_or_error(
        catalog_service.update_book(
            book_id,
            request.model_dump(
                exclude_unset=True
            ),
        ),
        "The book could not be updated.",
    )

    return result


# ============================================================
# ADMIN: IMPORT BOOKS FROM CSV
# ============================================================

@app.post(
    "/api/admin/books/import",
    response_model=AdminBookImportResult,
)
def admin_import_books(
    request: AdminBookImportRequest,
    x_session_id: str | None = Header(
        default=None
    ),
):

    require_admin(
        x_session_id
    )

    result = admin_result_or_error(
        catalog_service.import_books_csv(
            request.csv_text
        ),
        "The CSV import could "
        "not be completed.",
    )

    return result