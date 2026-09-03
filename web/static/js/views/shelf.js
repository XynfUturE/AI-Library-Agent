/* ============================================================
   SHELF VIEW — stats, loans, fines, history
   Read-only: mutations stay in the chat via the agent.
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

let loaded = false;

/** Data older than this is considered stale on re-entry. */
const SHELF_TTL_MS = 30 * 1000;

/** Timestamp (ms) of the last successful full load. */
let lastLoadedAt = 0;


function cacheElements() {

    els.stats = document.getElementById("shelf-stats");
    els.loansList = document.getElementById("loans-list");
    els.loansCount = document.getElementById("loans-count");
    els.finesList = document.getElementById("fines-list");
    els.finesCount = document.getElementById("fines-count");
    els.historyBody = document.getElementById("history-body");
    els.historyCount = document.getElementById("history-count");
    els.refreshButton = document.getElementById("shelf-refresh");
}


/* --------------------------------------------------------
   Helpers
   -------------------------------------------------------- */

function parseDate(value) {

    if (!value) {

        return null;
    }

    const date = new Date(String(value).replace(" ", "T"));

    return Number.isNaN(date.getTime()) ? null : date;
}


function formatDate(value) {

    const date = parseDate(value);

    if (!date) {

        return "—";
    }

    return date.toLocaleDateString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
    });
}


function formatMoney(amount) {

    return `$${Number(amount || 0).toFixed(2)}`;
}


function daysUntil(value) {

    const due = parseDate(value);

    if (!due) {

        return null;
    }

    const startOfDue = new Date(due);

    startOfDue.setHours(0, 0, 0, 0);

    const startOfNow = new Date();

    startOfNow.setHours(0, 0, 0, 0);

    return Math.round(
        (startOfDue.getTime() - startOfNow.getTime()) / 86400000
    );
}


function dueBadge(loan) {

    if (loan.is_overdue) {

        const days = Math.max(loan.late_days || 1, 1);

        return `<span class="badge badge-danger">${icon("alert", "icon icon-sm")}Overdue ${days}d</span>`;
    }

    const days = daysUntil(loan.due_date);

    if (days === null) {

        return `<span class="badge badge-neutral">On loan</span>`;
    }

    if (days === 0) {

        return `<span class="badge badge-warning">Due today</span>`;
    }

    if (days < 0) {

        return `<span class="badge badge-danger">Overdue ${Math.abs(days)}d</span>`;
    }

    return `<span class="badge badge-info">Due in ${days}d</span>`;
}


function askAgent(prompt) {

    document.dispatchEvent(
        new CustomEvent("chat:prompt", { detail: prompt })
    );
}


function emptyState(message, iconName) {

    return `
        <div class="empty-state">
            ${icon(iconName, "icon")}
            <span>${escapeHtml(message)}</span>
        </div>
    `;
}


/* --------------------------------------------------------
   Stat cards
   -------------------------------------------------------- */

function renderStats(summary) {

    const fineTotal = Number(summary.unpaid_fines_total || 0);

    const cards = [
        {
            value: summary.active_loans,
            label: "Active loans",
            iconName: "book",
            modifier: "",
        },
        {
            value: summary.overdue_count,
            label: "Overdue",
            iconName: "alert",
            modifier: summary.overdue_count > 0 ? "alerting" : "",
        },
        {
            value: formatMoney(fineTotal),
            label: "Unpaid fines",
            iconName: "coin",
            modifier: fineTotal > 0 ? "warning" : "",
        },
        {
            value: summary.total_borrowed,
            label: "Total borrowed",
            iconName: "history",
            modifier: "",
        },
    ];

    els.stats.innerHTML = cards
        .map(card => `
            <div class="stat-card ${card.modifier}">
                <span class="stat-icon">${icon(card.iconName, "icon icon-lg")}</span>
                <div>
                    <div class="stat-value num">${escapeHtml(String(card.value))}</div>
                    <div class="stat-label">${escapeHtml(card.label)}</div>
                </div>
            </div>
        `)
        .join("");
}


function renderStatsSkeleton() {

    els.stats.innerHTML = `
        <div class="skeleton skeleton-stat"></div>
        <div class="skeleton skeleton-stat"></div>
        <div class="skeleton skeleton-stat"></div>
        <div class="skeleton skeleton-stat"></div>
    `;
}


/* --------------------------------------------------------
   Loans & fines
   -------------------------------------------------------- */

function renderLoans(loans) {

    els.loansCount.textContent = String(loans.length);

    if (loans.length === 0) {

        els.loansList.innerHTML = emptyState(
            "Nothing on loan right now.",
            "book"
        );

        return;
    }

    els.loansList.innerHTML = loans
        .map(loan => `
            <div class="loan-row">
                <span class="loan-icon">${icon("book", "icon")}</span>
                <div class="loan-info">
                    <div class="loan-title">${escapeHtml(loan.book_title)}</div>
                    <div class="loan-meta">
                        Borrowed ${formatDate(loan.borrowed_at)}
                        · Due ${formatDate(loan.due_date)}
                    </div>
                </div>
                ${dueBadge(loan)}
                <button type="button" class="button button-ghost button-small loan-action"
                        data-title="${escapeHtml(loan.book_title)}">
                    ${icon("chat", "icon icon-sm")}
                    Return
                </button>
            </div>
        `)
        .join("");

    els.loansList.querySelectorAll(".loan-action").forEach(button => {

        button.addEventListener("click", () => {

            askAgent(
                `Please return "${button.dataset.title}" for me.`
            );
        });
    });
}


function renderFines(fines) {

    els.finesCount.textContent = String(fines.length);

    if (fines.length === 0) {

        els.finesList.innerHTML = emptyState(
            "You're all settled up.",
            "check"
        );

        return;
    }

    els.finesList.innerHTML = fines
        .map(fine => `
            <div class="fine-row">
                <span class="fine-icon">${icon("coin", "icon")}</span>
                <div class="fine-info">
                    <div class="fine-title">${escapeHtml(fine.book_title)}</div>
                    <div class="fine-meta">Returned ${formatDate(fine.returned_at)}</div>
                </div>
                <span class="fine-amount num">${formatMoney(fine.fine_amount)}</span>
                <button type="button" class="button button-ghost button-small fine-action"
                        data-title="${escapeHtml(fine.book_title)}"
                        data-amount="${Number(fine.fine_amount || 0).toFixed(2)}">
                    ${icon("chat", "icon icon-sm")}
                    Pay
                </button>
            </div>
        `)
        .join("");

    els.finesList.querySelectorAll(".fine-action").forEach(button => {

        button.addEventListener("click", () => {

            askAgent(
                `Please pay my fine of $${button.dataset.amount} for "${button.dataset.title}".`
            );
        });
    });
}


function renderHistory(history) {

    els.historyCount.textContent = String(history.length);

    if (history.length === 0) {

        els.historyBody.innerHTML = `
            <tr>
                <td colspan="4">
                    ${emptyState("No borrowing history yet.", "history")}
                </td>
            </tr>
        `;

        return;
    }

    els.historyBody.innerHTML = history
        .map(item => {

            const fine = Number(item.fine_amount || 0);

            const fineCell = fine > 0
                ? `${formatMoney(fine)} ${item.fine_paid
                    ? `<span class="badge badge-success">Paid</span>`
                    : `<span class="badge badge-warning">Unpaid</span>`}`
                : `<span class="badge badge-neutral">None</span>`;

            return `
                <tr>
                    <td class="book-cell">
                        <strong>${escapeHtml(item.book_title)}</strong>
                        <span>${escapeHtml(item.author || "")}</span>
                    </td>
                    <td>${formatDate(item.borrowed_at)}</td>
                    <td>${item.returned_at ? formatDate(item.returned_at) : "—"}</td>
                    <td>${fineCell}</td>
                </tr>
            `;
        })
        .join("");
}


/* --------------------------------------------------------
   Load everything
   -------------------------------------------------------- */

export async function loadShelf(force = false) {

    if (!state.sessionId) {

        return;
    }

    // Re-entering the shelf within the TTL can reuse the rendered panel:
    // skip the 4-request refetch unless the user explicitly refreshes.
    if (!force && loaded && Date.now() - lastLoadedAt < SHELF_TTL_MS) {

        return;
    }

    if (force || !loaded) {

        renderStatsSkeleton();
    }

    try {

        const [summary, loans, fines, history] = await Promise.all([
            api("/api/shelf/summary"),
            api("/api/shelf/loans"),
            api("/api/shelf/fines"),
            api("/api/shelf/history"),
        ]);

        renderStats(summary);
        renderLoans(loans.items || []);
        renderFines(fines.items || []);
        renderHistory(history.items || []);

        loaded = true;
        lastLoadedAt = Date.now();

    } catch (error) {

        if (!loaded) {

            els.stats.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    ${icon("alert", "icon")}
                    <span>Your shelf could not be loaded.</span>
                </div>
            `;
        }

        toast(error.message, "error");
    }
}


/* --------------------------------------------------------
   Init
   -------------------------------------------------------- */

export function initShelf() {

    cacheElements();

    els.refreshButton.addEventListener("click", () => loadShelf(true));

    document.addEventListener("route:changed", event => {

        if (event.detail.route === "shelf") {

            // Non-forced: within the TTL the rendered panel is reused,
            // so quick back-and-forth navigation does not refetch 4 APIs.
            loadShelf();
        }
    });

    // Session changes (login as another user / logout) must not leak
    // the previous user's cached shelf into the next session.
    const invalidateCache = () => {

        loaded = false;
        lastLoadedAt = 0;
    };

    document.addEventListener("session:logged-out", invalidateCache);
    document.addEventListener("session:expired", invalidateCache);
    document.addEventListener("session:established", invalidateCache);
}
