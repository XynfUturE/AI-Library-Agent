/* ============================================================
   CATALOG VIEW — classified directory with category sidebar,
   search / availability filters, grid & list modes.
   Administrators can add / edit books and bulk-import CSV.
   Members borrow by dispatching a prompt to the chat agent.
   ============================================================ */

import {
    api,
} from "../lib/api.js";

import {
    state,
} from "../lib/state.js";

import {
    toast,
} from "../lib/toast.js";

import {
    icon,
} from "../lib/icons.js";

import {
    escapeHtml,
} from "../lib/markdown.js";


const els = {};

/** Client-side view state for the current session. */
const filters = {
    keyword: "",
    categoryId: null,
    availability: "",
};

/** Category tree cache for the current session (id -> node). */
let categoryData = null;

/** Flat lookup for labels & options (id -> { name, path }). */
let categoryLookup = null;

/** Resolved sidebar structure: [ { id, name, count, children:[...] }, ... ]. */
let sidebarNodes = [];

/** Currently expanded top-level group ids. */
const openGroups = new Set();

let viewMode = "grid";

let keywordTimer = null;

/** Guards against out-of-order responses during typing. */
let requestSerial = 0;

/** Session lifecycle cache flag. */
let loadedOnce = false;

const TTL_MS = 45 * 1000;

let lastLoadedAt = 0;

let editingBookId = null;


/* --------------------------------------------------------
   Boot & caching
   -------------------------------------------------------- */

function cacheElements() {

    els.catalogView = document.getElementById("view-catalog");
    els.categoryNav = document.getElementById("catalog-category-nav");
    els.keywordInput = document.getElementById("catalog-keyword");
    els.clearSearch = document.getElementById("catalog-clear-search");
    els.availabilitySelect = document.getElementById("catalog-availability");
    els.viewGrid = document.getElementById("catalog-view-grid");
    els.viewList = document.getElementById("catalog-view-list");
    els.results = document.getElementById("catalog-results");
    els.loading = document.getElementById("catalog-loading");
    els.addButton = document.getElementById("catalog-add-button");
    els.filterSummary = document.getElementById("catalog-filter-summary");
    els.resultsCount = document.getElementById("catalog-results-count");
}


function isAdmin() {

    return state.role === "admin";
}


function invalidateCache() {

    loadedOnce = false;
    lastLoadedAt = 0;
    categoryData = null;
    categoryLookup = null;
    sidebarNodes = [];
    openGroups.clear();
    filters.keyword = "";
    filters.categoryId = null;
    filters.availability = "";
}


function syncAdminUI() {

    if (els.addButton) {

        els.addButton.classList.toggle("hidden", !isAdmin());
    }
}


/* --------------------------------------------------------
   Book helpers
   -------------------------------------------------------- */

function coverStyle(title) {

    let hash = 0;

    for (const char of String(title)) {

        hash = (hash * 31 + char.charCodeAt(0)) % 100000;
    }

    const hue = hash % 360;

    return `background: linear-gradient(135deg, hsl(${hue} 62% 52%), hsl(${(hue + 45) % 360} 62% 40%));`;
}


/**
 * Render the cover area for a book card/row. A real cover image is used
 * when available; otherwise a deterministic gradient placeholder is shown.
 */
function coverElement(book, className) {

    const gradient = coverStyle(book.title);

    if (book.cover_url) {

        return `
            <div class="${className} has-cover" style="${gradient}">
                <img class="${className}-img" src="${escapeHtml(book.cover_url)}"
                     alt="${escapeHtml(book.title)} cover" loading="lazy"
                     onerror="this.remove()">
            </div>
        `;
    }

    return `
        <div class="${className}" style="${gradient}">
            ${icon("book", "icon")}
        </div>
    `;
}


function availabilityBadge(book) {

    return book.available
        ? `<span class="badge badge-success">${icon("check", "icon icon-sm")}Available</span>`
        : `<span class="badge badge-neutral">${icon("clock", "icon icon-sm")}On loan</span>`;
}


function borrowButton(book) {

    if (!book.available) {

        return "";
    }

    return `
        <button type="button" class="button button-secondary button-small borrow-action"
                data-id="${book.id}"
                data-title="${escapeHtml(book.title)}"
                data-author="${escapeHtml(book.author)}">
            Borrow
        </button>
    `;
}


function adminEditButton(book) {

    if (!isAdmin()) {

        return "";
    }

    return `
        <button type="button" class="button button-ghost button-small book-edit-action"
                data-id="${book.id}" title="Edit book">
            ${icon("edit", "icon icon-sm")}
        </button>
    `;
}


function emptyMessage(text, iconName) {

    return `
        <div class="empty-state">
            ${icon(iconName, "icon")}
            <span>${escapeHtml(text)}</span>
        </div>
    `;
}


/* --------------------------------------------------------
   Results rendering
   -------------------------------------------------------- */

function bookCard(book) {

    return `
        <article class="book-card" data-book-id="${book.id}">
            ${coverElement(book, "book-cover")}
            <div class="book-card-body">
                <div class="book-title" title="${escapeHtml(book.title)}">${escapeHtml(book.title)}</div>
                <div class="book-author">${escapeHtml(book.author)}</div>
                ${book.category_label
                    ? `<div class="book-category">${escapeHtml(book.category_label)}</div>`
                    : ""}
                <div class="book-card-footer">
                    ${availabilityBadge(book)}
                    <span class="book-actions">
                        ${borrowButton(book)}
                        ${adminEditButton(book)}
                    </span>
                </div>
            </div>
        </article>
    `;
}


function bookRow(book) {

    const metaParts = [];

    if (book.category_label) {

        metaParts.push(escapeHtml(book.category_label));
    }

    if (book.isbn) {

        metaParts.push(`ISBN ${escapeHtml(book.isbn)}`);
    }

    if (book.publisher) {

        metaParts.push(escapeHtml(book.publisher));
    }

    const snippet = (book.description || "").trim();

    return `
        <article class="book-row" data-book-id="${book.id}">
            ${coverElement(book, "book-thumb")}
            <div class="book-row-info">
                <div class="book-row-title">${escapeHtml(book.title)}</div>
                <div class="book-row-author">${escapeHtml(book.author)}</div>
                ${metaParts.length
                    ? `<div class="book-row-meta">${metaParts.join(" · ")}</div>`
                    : ""}
                ${snippet
                    ? `<div class="book-row-snippet">${escapeHtml(snippet)}</div>`
                    : ""}
            </div>
            <div class="book-row-side">
                ${availabilityBadge(book)}
                <div class="book-row-actions">
                    ${borrowButton(book)}
                    ${adminEditButton(book)}
                </div>
            </div>
        </article>
    `;
}


function renderResults(books) {

    els.results.classList.toggle("catalog-grid", viewMode === "grid");
    els.results.classList.toggle("catalog-list", viewMode === "list");

    els.resultsCount.textContent = `${books.length} book${books.length === 1 ? "" : "s"}`;

    if (books.length === 0) {

        els.results.innerHTML = emptyMessage(
            "No books match the current filters.",
            "search"
        );

        return;
    }

    const render = viewMode === "grid" ? bookCard : bookRow;

    els.results.innerHTML = books.map(render).join("");

    els.results.querySelectorAll(".borrow-action").forEach(button => {

        button.addEventListener("click", () => {

            askAgent(
                `Please borrow "${button.dataset.title}" by ${button.dataset.author} for me.`
            );
        });
    });

    els.results.querySelectorAll(".book-edit-action").forEach(button => {

        button.addEventListener("click", () => {

            const book = books.find(item => item.id === Number(button.dataset.id));

            if (book) {

                openBookForm(book);
            }
        });
    });
}


function renderLoading() {

    els.results.classList.add("hidden");
    els.loading.classList.remove("hidden");
}


function clearLoading() {

    els.results.classList.remove("hidden");
    els.loading.classList.add("hidden");
}


/* --------------------------------------------------------
   Load books
   -------------------------------------------------------- */

function filterSummaryText() {

    const parts = [];

    if (filters.keyword) {

        parts.push(`“${filters.keyword}”`);
    }

    const categoryName = categoryNameFor(filters.categoryId);

    if (filters.categoryId !== null) {

        parts.push(categoryName || "Category");
    }

    if (filters.availability === "available") {

        parts.push("Available");
    } else if (filters.availability === "loaned") {

        parts.push("On loan");
    }

    return parts.length ? parts.join(" · ") : "All Books";
}


function categoryNameFor(categoryId) {

    if (categoryId === null) {

        return null;
    }

    return (categoryLookup && categoryLookup[categoryId])
        ? categoryLookup[categoryId].label
        : null;
}


async function loadBooks() {

    if (!state.sessionId) {

        return;
    }

    const serial = ++requestSerial;

    renderLoading();

    const params = new URLSearchParams();

    if (filters.keyword) {

        params.set("q", filters.keyword);
    }

    if (filters.categoryId !== null) {

        params.set("category_id", String(filters.categoryId));
    }

    if (filters.availability) {

        params.set("availability", filters.availability);
    }

    els.filterSummary.textContent = filterSummaryText();

    try {

        const data = await api(`/api/catalog/books?${params.toString()}`);

        if (serial !== requestSerial) {

            return; // A newer request superseded this one.
        }

        clearLoading();

        renderResults(data.items || []);

    } catch (error) {

        if (serial !== requestSerial) {

            return;
        }

        clearLoading();

        els.results.innerHTML = emptyMessage(
            error.message || "The catalog could not be loaded.",
            "alert"
        );

        toast(error.message, "error");
    }
}


/* --------------------------------------------------------
   Categories
   -------------------------------------------------------- */

async function fetchCategories(force) {

    if (
        !force
        && categoryData
        && loadedOnce
        && Date.now() - lastLoadedAt < TTL_MS
    ) {

        return categoryData;
    }

    const data = await api("/api/catalog/categories");

    categoryData = data;

    // Flat lookup by id with a readable two-level label.
    categoryLookup = {};

    const tree = (data.categories || []).map(group => {

        const node = {
            id: group.id,
            name: group.name,
            count: group.book_count || 0,
            children: (group.children || []).map(child => {

                categoryLookup[child.id] = {
                    name: child.name,
                    label: `${group.name} / ${child.name}`,
                };

                return {
                    id: child.id,
                    name: child.name,
                    count: child.book_count || 0,
                };
            }),
        };

        categoryLookup[node.id] = {
            name: node.name,
            label: node.name,
        };

        return node;
    });

    sidebarNodes = tree;

    return data;
}


function renderCategories() {

    const total = categoryData ? categoryData.total : 0;

    const active = filters.categoryId;

    const chip = count => `<span class="cat-count">${Number(count)}</span>`;

    const selectCls = id => (
        (id === active || (id === null && active === null))
            ? "cat-select active"
            : "cat-select"
    );

    const parts = [];

    // ---- All Books --------------------------------------
    parts.push(`
        <button type="button" class="${selectCls(null)}" data-id="all">
            ${icon("book", "icon icon-sm")}
            <span class="cat-name">All Books</span>
            ${chip(total)}
        </button>
    `);

    // ---- Category groups ----------------------------------
    for (const group of sidebarNodes) {

        const isOpen = openGroups.has(group.id);

        const isActiveGroup = active === group.id;

        parts.push(`
            <div class="category-node" data-group-id="${group.id}">

                <div class="category-row">
                    <button type="button" class="cat-toggle"
                            data-toggle="${group.id}"
                            aria-expanded="${isOpen ? "true" : "false"}">
                        <svg class="icon icon-sm chevron ${isOpen ? "open" : ""}">
                            <use href="#i-chevron-right"></use>
                        </svg>
                    </button>
                    <button type="button" class="${selectCls(group.id)}" data-id="${group.id}">
                        ${icon("folder", "icon icon-sm")}
                        <span class="cat-name">${escapeHtml(group.name)}</span>
                        ${chip(group.count)}
                    </button>
                </div>

                <div class="category-children ${isOpen ? "" : "hidden"}">
                    ${group.children.map(child => `
                        <button type="button" class="${selectCls(child.id)} cat-child"
                                data-id="${child.id}">
                            <span class="cat-bullet"></span>
                            <span class="cat-name">${escapeHtml(child.name)}</span>
                            ${chip(child.count)}
                        </button>
                    `).join("")}
                </div>

            </div>
        `);
    }

    els.categoryNav.innerHTML = parts.join("");

    // Selecting a category updates the filter and reloads.
    els.categoryNav.querySelectorAll(".cat-select").forEach(button => {

        button.addEventListener("click", () => {

            const raw = button.dataset.id;

            filters.categoryId = raw === "all" ? null : Number(raw);

            renderCategories();

            loadBooks();
        });
    });

    // Expanding / collapsing a group only changes visibility.
    els.categoryNav.querySelectorAll(".cat-toggle").forEach(button => {

        button.addEventListener("click", () => {

            const groupId = Number(button.dataset.toggle);

            if (openGroups.has(groupId)) {

                openGroups.delete(groupId);

            } else {

                openGroups.add(groupId);
            }

            renderCategories();
        });
    });
}


async function loadCategories(force) {

    if (!state.sessionId) {

        return;
    }

    try {

        await fetchCategories(force);

        renderCategories();

    } catch (error) {

        els.categoryNav.innerHTML = `
            <div class="empty-state">
                ${icon("alert", "icon")}
                <span>Categories could not be loaded.</span>
            </div>
        `;

        toast(error.message, "error");
    }
}


/* --------------------------------------------------------
   Entering the catalog view
   -------------------------------------------------------- */

async function enterCatalog() {

    if (!state.sessionId) {

        return;
    }

    syncAdminUI();

    const isStale = (
        !loadedOnce
        || Date.now() - lastLoadedAt > TTL_MS
    );

    try {

        await fetchCategories(isStale);

        loadedOnce = true;
        lastLoadedAt = Date.now();

        renderCategories();

        // The grid keeps its filters across visits within the
        // session, but always re-queries so data stays fresh.
        loadBooks();

    } catch (error) {

        toast(error.message, "error");
    }
}


/* --------------------------------------------------------
   Chat handoff (borrow)
   -------------------------------------------------------- */

function askAgent(prompt) {

    document.dispatchEvent(
        new CustomEvent("chat:prompt", { detail: prompt })
    );
}


/* --------------------------------------------------------
   Book form dialog (add / edit)
   -------------------------------------------------------- */

function categoryOptions(selectedId) {

    const options = [
        `<option value="">Select a category…</option>`,
    ];

    for (const group of sidebarNodes) {

        options.push(`<option value="${group.id}" ${group.id === selectedId ? "selected" : ""}>${escapeHtml(group.name)}</option>`);

        for (const child of group.children) {

            options.push(`<option value="${child.id}" ${child.id === selectedId ? "selected" : ""}>&nbsp;&nbsp;${escapeHtml(group.name)} / ${escapeHtml(child.name)}</option>`);
        }
    }

    return options.join("");
}


function buildBookFormPane() {

    return `
        <form id="catalog-book-form" class="catalog-book-form" novalidate>

            <div class="form-grid">

                <div class="form-group">
                    <label for="catalog-field-title">Title *</label>
                    <input id="catalog-field-title" class="input" type="text" required
                           placeholder="Book title">
                </div>

                <div class="form-group">
                    <label for="catalog-field-author">Author *</label>
                    <input id="catalog-field-author" class="input" type="text" required
                           placeholder="Author name">
                </div>

                <div class="form-group">
                    <label for="catalog-field-category">Category</label>
                    <select id="catalog-field-category" class="input"></select>
                </div>

                <div class="form-group">
                    <label for="catalog-field-isbn">ISBN <span class="optional-hint">(optional)</span></label>
                    <input id="catalog-field-isbn" class="input" type="text" placeholder="e.g. 978-7-…">
                </div>

                <div class="form-group">
                    <label for="catalog-field-publisher">Publisher <span class="optional-hint">(optional)</span></label>
                    <input id="catalog-field-publisher" class="input" type="text">
                </div>

                <div class="form-group">
                    <label for="catalog-field-pubdate">Publication date <span class="optional-hint">(optional)</span></label>
                    <input id="catalog-field-pubdate" class="input" type="text" placeholder="e.g. 2024-05">
                </div>

                <div class="form-group">
                    <label for="catalog-field-language">Language <span class="optional-hint">(optional)</span></label>
                    <input id="catalog-field-language" class="input" type="text" placeholder="e.g. Chinese">
                </div>

                <div class="form-group">
                    <label for="catalog-field-location">Location <span class="optional-hint">(optional)</span></label>
                    <input id="catalog-field-location" class="input" type="text" placeholder="e.g. 3F / Science">
                </div>

                <div class="form-group form-span">
                    <label for="catalog-field-cover">Cover URL <span class="optional-hint">(optional)</span></label>
                    <input id="catalog-field-cover" class="input" type="url" placeholder="https://…">
                </div>

                <div class="form-group form-span">
                    <label for="catalog-field-description">Description <span class="optional-hint">(optional)</span></label>
                    <textarea id="catalog-field-description" class="input catalog-textarea" rows="3"></textarea>
                </div>

            </div>

            <label class="check-row">
                <input id="catalog-field-available" type="checkbox" checked>
                <span>Available for loan</span>
            </label>

            <div id="catalog-form-message" class="message-area" role="alert"></div>

            <div class="dialog-actions">
                <button type="button" class="button button-ghost dialog-cancel">Cancel</button>
                <button type="submit" class="button button-primary">Save book</button>
            </div>

        </form>
    `;
}


function buildCsvPane() {

    return `
        <div class="csv-pane">

            <p class="csv-hint">
                Upload a CSV file or paste its contents. The first row must be a header;
                columns <code>title</code> and <code>author</code> are required. Localized
                header names are accepted as well.
                The <code>category</code> column accepts a top-level name, a leaf name,
                or <code>Parent / Child</code>.
            </p>

            <div class="csv-file-row">
                <input id="catalog-csv-file" class="csv-file-input" type="file"
                       accept=".csv,text/csv" aria-label="Choose a CSV file">
                <span id="catalog-csv-filename" class="csv-filename">No file chosen</span>
            </div>

            <textarea id="catalog-csv-text" class="input catalog-textarea catalog-csv-text"
                      rows="8" spellcheck="false"
                      placeholder="title,author,category,isbn,publisher,available&#10;The Silent Garden,Elena Stone,Literature &amp; Fiction / Sci-Fi &amp; Fantasy,,,1"></textarea>

            <div id="catalog-csv-message" class="message-area" role="alert"></div>

            <div id="catalog-csv-errors" class="csv-errors hidden"></div>

            <div class="dialog-actions">
                <button type="button" class="button button-ghost dialog-cancel">Cancel</button>
                <button type="button" id="catalog-csv-submit" class="button button-primary">
                    ${icon("upload", "icon icon-sm")}
                    Import CSV
                </button>
            </div>

        </div>
    `;
}


function showFormMessage(area, message, type) {

    area.className = `message-area ${type}`;

    area.textContent = message;
}


function setBusyButton(button, busy, busyLabel) {

    if (!button) {

        return;
    }

    if (busy) {

        button.dataset.restore = button.innerHTML;

        button.disabled = true;

        button.textContent = busyLabel;

    } else {

        button.disabled = false;

        if (button.dataset.restore) {

            button.innerHTML = button.dataset.restore;
        }
    }
}


function switchDialogPane(mode) {

    els.dialogManualPane.classList.toggle("hidden", mode !== "manual");
    els.dialogCsvPane.classList.toggle("hidden", mode !== "csv");

    document.querySelectorAll(".dialog-tab").forEach(tab => {

        const tabMode = tab.dataset.mode;

        tab.classList.toggle("active", tabMode === mode);
    });
}


function openDialog(title, showTabs) {

    els.dialogTitle.textContent = title;

    els.dialogTabs.classList.toggle("hidden", !showTabs);

    els.dialogOverlay.classList.remove("hidden");

    document.body.classList.add("modal-open");
}


function closeDialog() {

    els.dialogOverlay.classList.add("hidden");

    document.body.classList.remove("modal-open");

    editingBookId = null;
}


function fillCategoryOptions(selectedId) {

    const select = document.getElementById("catalog-field-category");

    if (select) {

        select.innerHTML = categoryOptions(selectedId || null);
    }
}


async function openBookForm(book) {

    await fetchCategories(false);

    editingBookId = book ? book.id : null;

    els.dialogManualPane.innerHTML = buildBookFormPane();

    els.dialogCsvPane.innerHTML = buildCsvPane();

    fillCategoryOptions(book ? book.category_id : null);

    const form = document.getElementById("catalog-book-form");

    if (book) {

        form.elements["catalog-field-title"].value = book.title || "";
        form.elements["catalog-field-author"].value = book.author || "";
        form.elements["catalog-field-isbn"].value = book.isbn || "";
        form.elements["catalog-field-publisher"].value = book.publisher || "";
        form.elements["catalog-field-pubdate"].value = book.pub_date || "";
        form.elements["catalog-field-language"].value = book.language || "";
        form.elements["catalog-field-location"].value = book.location || "";
        form.elements["catalog-field-cover"].value = book.cover_url || "";
        form.elements["catalog-field-description"].value = book.description || "";

        document.getElementById("catalog-field-available").checked = Boolean(book.available);

        openDialog("Edit book", false);

    } else {

        openDialog("Add book", true);
    }

    // Wire dialog-level controls (pane is freshly created).
    els.dialogOverlay.querySelectorAll(".dialog-tab").forEach(tab => {

        tab.addEventListener("click", () => switchDialogPane(tab.dataset.mode));
    });

    els.dialogOverlay.querySelectorAll(".dialog-cancel").forEach(button => {

        button.addEventListener("click", closeDialog);
    });

    // Manual form submission ---------------------------------
    form.addEventListener("submit", async event => {

        event.preventDefault();

        const messageArea = document.getElementById("catalog-form-message");

        const submitButton = form.querySelector('button[type="submit"]');

        const body = {
            title: form.elements["catalog-field-title"].value.trim(),
            author: form.elements["catalog-field-author"].value.trim(),
            category_id: form.elements["catalog-field-category"].value || null,
            isbn: form.elements["catalog-field-isbn"].value.trim(),
            publisher: form.elements["catalog-field-publisher"].value.trim(),
            pub_date: form.elements["catalog-field-pubdate"].value.trim(),
            language: form.elements["catalog-field-language"].value.trim(),
            location: form.elements["catalog-field-location"].value.trim(),
            cover_url: form.elements["catalog-field-cover"].value.trim(),
            description: form.elements["catalog-field-description"].value.trim(),
            available: document.getElementById("catalog-field-available").checked,
        };

        setBusyButton(submitButton, true, editingBookId ? "Saving…" : "Adding…");

        try {

            if (editingBookId) {

                await api(`/api/admin/books/${editingBookId}`, {
                    method: "PUT",
                    body,
                });

            } else {

                await api("/api/admin/books", {
                    method: "POST",
                    body,
                });
            }

            toast(editingBookId ? "Book updated." : "Book added.", "success");

            closeDialog();

            loadedOnce = false;

            loadCategories(true);

            loadBooks();

        } catch (error) {

            showFormMessage(messageArea, error.message, "error");

        } finally {

            setBusyButton(submitButton, false);
        }
    });

    // CSV import ----------------------------------------------
    const fileInput = document.getElementById("catalog-csv-file");
    const fileLabel = document.getElementById("catalog-csv-filename");
    const csvText = document.getElementById("catalog-csv-text");
    const csvMessage = document.getElementById("catalog-csv-message");
    const csvErrors = document.getElementById("catalog-csv-errors");
    const csvSubmit = document.getElementById("catalog-csv-submit");

    if (fileInput) {

        fileInput.addEventListener("change", () => {

            const file = fileInput.files && fileInput.files[0];

            if (!file) {

                return;
            }

            fileLabel.textContent = file.name;

            const reader = new FileReader();

            reader.onload = () => {

                csvText.value = String(reader.result || "");
            };

            reader.readAsText(file);
        });
    }

    csvSubmit.addEventListener("click", async () => {

        csvErrors.classList.add("hidden");

        csvErrors.innerHTML = "";

        showFormMessage(csvMessage, "", "");

        const text = csvText.value.trim();

        if (!text) {

            showFormMessage(csvMessage, "Please choose a CSV file or paste CSV content.", "error");

            return;
        }

        setBusyButton(csvSubmit, true, "Importing…");

        try {

            const result = await api("/api/admin/books/import", {
                method: "POST",
                body: { csv_text: text },
            });

            const errors = result.errors || [];

            const skipped = errors.length;

            if (skipped > 0) {

                showFormMessage(
                    csvMessage,
                    `${result.inserted} imported, ${skipped} skipped.`,
                    skipped === result.total_rows ? "error" : "success"
                );

                csvErrors.classList.remove("hidden");

                csvErrors.innerHTML = `
                    <div class="csv-error-title">Row errors</div>
                    <ul>
                        ${errors.map(error => `
                            <li><strong>Line ${error.line}:</strong> ${escapeHtml(error.message)}</li>
                        `).join("")}
                    </ul>
                `;

            } else {

                showFormMessage(
                    csvMessage,
                    result.message || "Import complete.",
                    "success"
                );

                csvText.value = "";

                if (fileInput) {

                    fileInput.value = "";

                    fileLabel.textContent = "No file chosen";
                }
            }

            toast(result.message || "Import finished.", skipped ? "warning" : "success");

            loadedOnce = false;

            loadCategories(true);

            loadBooks();

        } catch (error) {

            showFormMessage(csvMessage, error.message, "error");

        } finally {

            setBusyButton(csvSubmit, false);
        }
    });
}


/* --------------------------------------------------------
   Init
   -------------------------------------------------------- */

function buildDialogHost() {

    const host = document.createElement("div");

    host.id = "catalog-dialog-host";

    host.innerHTML = `
        <div id="catalog-dialog-overlay" class="dialog-overlay hidden" role="dialog"
             aria-modal="true" aria-labelledby="catalog-dialog-title">

            <div class="dialog">

                <header class="dialog-head">
                    <h2 id="catalog-dialog-title">Add book</h2>
                    <button type="button" class="icon-button" id="catalog-dialog-close"
                            aria-label="Close dialog">
                        <svg class="icon"><use href="#i-x"></use></svg>
                    </button>
                </header>

                <div id="catalog-dialog-tabs" class="dialog-tabs">
                    <button type="button" class="dialog-tab active" data-mode="manual">
                        ${icon("edit", "icon icon-sm")}
                        Single entry
                    </button>
                    <button type="button" class="dialog-tab" data-mode="csv">
                        ${icon("upload", "icon icon-sm")}
                        CSV import
                    </button>
                </div>

                <div id="catalog-dialog-manual" class="dialog-pane"></div>

                <div id="catalog-dialog-csv" class="dialog-pane hidden"></div>

            </div>

        </div>
    `;

    document.body.appendChild(host);

    els.dialogOverlay = document.getElementById("catalog-dialog-overlay");
    els.dialogTitle = document.getElementById("catalog-dialog-title");
    els.dialogTabs = document.getElementById("catalog-dialog-tabs");
    els.dialogManualPane = document.getElementById("catalog-dialog-manual");
    els.dialogCsvPane = document.getElementById("catalog-dialog-csv");

    document.getElementById("catalog-dialog-close").addEventListener("click", closeDialog);

    els.dialogOverlay.addEventListener("click", event => {

        if (event.target === els.dialogOverlay) {

            closeDialog();
        }
    });

    document.addEventListener("keydown", event => {

        if (event.key === "Escape" && !els.dialogOverlay.classList.contains("hidden")) {

            closeDialog();
        }
    });
}


export function initCatalog() {

    cacheElements();

    buildDialogHost();

    syncAdminUI();

    // Add book (admin only) --------------------------------
    els.addButton.addEventListener("click", () => openBookForm(null));

    // Keyword search (debounced) ----------------------------
    els.keywordInput.addEventListener("input", () => {

        const value = els.keywordInput.value.trim();

        els.clearSearch.classList.toggle("hidden", !value);

        clearTimeout(keywordTimer);

        keywordTimer = setTimeout(() => {

            filters.keyword = value;

            loadBooks();

        }, 320);
    });

    els.keywordInput.addEventListener("keydown", event => {

        if (event.key === "Enter") {

            event.preventDefault();

            clearTimeout(keywordTimer);

            filters.keyword = els.keywordInput.value.trim();

            loadBooks();
        }
    });

    els.clearSearch.addEventListener("click", () => {

        els.keywordInput.value = "";

        els.clearSearch.classList.add("hidden");

        filters.keyword = "";

        loadBooks();
    });

    // Availability filter ------------------------------------
    els.availabilitySelect.addEventListener("change", () => {

        filters.availability = els.availabilitySelect.value;

        loadBooks();
    });

    // Grid / list toggle -------------------------------------
    function setViewMode(mode) {

        viewMode = mode;

        els.viewGrid.classList.toggle("active", mode === "grid");
        els.viewList.classList.toggle("active", mode === "list");

        if (!els.results.classList.contains("hidden")) {

            loadBooks(); // re-render in the new layout
        }
    }

    els.viewGrid.addEventListener("click", () => setViewMode("grid"));
    els.viewList.addEventListener("click", () => setViewMode("list"));

    // Routing -------------------------------------------------
    document.addEventListener("route:changed", event => {

        if (event.detail.route === "catalog") {

            syncAdminUI();

            enterCatalog();
        }
    });

    // Session changes reset all catalog caches.
    const invalidate = () => {

        requestSerial += 1;

        invalidateCache();

        if (!state.sessionId) {

            els.results.innerHTML = "";
        }

        syncAdminUI();
    };

    document.addEventListener("session:logged-out", invalidate);
    document.addEventListener("session:expired", invalidate);
    document.addEventListener("session:established", invalidate);
}
