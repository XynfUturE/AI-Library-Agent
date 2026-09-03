from pydantic import BaseModel


# ============================================================
# LOGIN
# ============================================================

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    user_id: int | None = None
    username: str | None = None
    role: str | None = None
    session_id: str | None = None


# ============================================================
# REGISTER
# ============================================================

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


# ============================================================
# CHAT
# ============================================================

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    success: bool
    reply: str


# ============================================================
# SESSION CHECK
# ============================================================

class SessionCheckResponse(BaseModel):
    success: bool
    user_id: int
    username: str
    full_name: str | None = None
    role: str | None = None


# ============================================================
# SHELF (READ-ONLY DASHBOARD)
# ============================================================

class ShelfSummaryResponse(BaseModel):
    success: bool
    active_loans: int
    overdue_count: int
    unpaid_fines_total: float
    total_borrowed: int


class ShelfItemsResponse(BaseModel):
    success: bool
    items: list[dict]


class CatalogResponse(BaseModel):
    success: bool
    items: list[dict]
    query: str | None = None


# ============================================================
# CATALOG (CLASSIFIED BOOK DIRECTORY)
# ============================================================

class CategoryNode(BaseModel):
    id: int
    name: str
    book_count: int = 0
    children: list["CategoryNode"] = []


class CatalogCategoriesResponse(BaseModel):
    success: bool
    total: int
    uncategorized: int = 0
    categories: list[CategoryNode]


class CatalogBook(BaseModel):
    id: int
    title: str
    author: str
    available: bool
    category_id: int | None = None
    category_label: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    pub_date: str | None = None
    language: str | None = None
    location: str | None = None
    description: str | None = None
    cover_url: str | None = None


class CatalogBooksResponse(BaseModel):
    success: bool
    items: list[CatalogBook]


# ============================================================
# ADMIN BOOK MANAGEMENT
# ============================================================

class AdminBookPayload(BaseModel):
    title: str
    author: str
    category_id: int | None = None
    isbn: str | None = None
    publisher: str | None = None
    pub_date: str | None = None
    language: str | None = None
    location: str | None = None
    cover_url: str | None = None
    description: str | None = None
    available: bool = True


class AdminBookUpdatePayload(BaseModel):
    title: str | None = None
    author: str | None = None
    category_id: int | None = None
    isbn: str | None = None
    publisher: str | None = None
    pub_date: str | None = None
    language: str | None = None
    location: str | None = None
    cover_url: str | None = None
    description: str | None = None
    available: bool | None = None


class AdminBookResult(BaseModel):
    success: bool
    message: str
    book: CatalogBook | None = None


class AdminBookImportRequest(BaseModel):
    csv_text: str


class AdminBookImportResult(BaseModel):
    success: bool
    message: str
    total_rows: int | None = None
    inserted: int | None = None
    skipped: int | None = None
    errors: list[dict] | None = None