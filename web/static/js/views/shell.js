/* ============================================================
   SHELL — sidebar, topbar, hash routing, logout
   ============================================================ */

import {
    api,
} from "../lib/api.js";

import {
    state,
    resetSession,
    toggleTheme,
    loadSidebarCollapsed,
    saveSidebarCollapsed,
} from "../lib/state.js";

import {
    toast,
} from "../lib/toast.js";

import {
    initialsOf,
} from "../lib/icons.js";

import {
    showLoginCard,
} from "./auth.js";


const ROUTES = {
    chat: { title: "Chat" },
    shelf: { title: "My Shelf" },
    catalog: { title: "Catalog" },
};

let els = {};

let currentRoute = "chat";


function cacheElements() {

    els.shell = document.getElementById("app-shell");
    els.authScreen = document.getElementById("auth-screen");
    els.sidebar = document.getElementById("sidebar");
    els.scrim = document.getElementById("sidebar-scrim");
    els.collapseButton = document.getElementById("sidebar-collapse-button");
    els.menuButton = document.getElementById("sidebar-toggle");
    els.topbarTitle = document.getElementById("topbar-title");
    els.userName = document.getElementById("user-name");
    els.userInitials = document.getElementById("user-initials");
    els.userRoleLabel = document.getElementById("user-role-label");
    els.logoutButton = document.getElementById("logout-button");
    els.viewChat = document.getElementById("view-chat");
    els.viewShelf = document.getElementById("view-shelf");
    els.viewCatalog = document.getElementById("view-catalog");
}


/* --------------------------------------------------------
   Mobile drawer
   -------------------------------------------------------- */

function openSidebar() {

    els.shell.classList.add("sidebar-open");
}


function closeSidebar() {

    els.shell.classList.remove("sidebar-open");
}


/* --------------------------------------------------------
   Routing
   -------------------------------------------------------- */

export function route() {

    if (!state.sessionId) {

        return;
    }

    const hash = location.hash.replace(/^#\/?/, "");

    const target = ROUTES[hash] ? hash : "chat";

    currentRoute = target;

    els.viewChat.classList.toggle("hidden", target !== "chat");
    els.viewShelf.classList.toggle("hidden", target !== "shelf");
    els.viewCatalog.classList.toggle("hidden", target !== "catalog");

    els.topbarTitle.textContent = ROUTES[target].title;

    document.querySelectorAll(".nav-item[data-route]").forEach(item => {

        item.classList.toggle(
            "active",
            item.dataset.route === target
        );
    });

    closeSidebar();

    document.dispatchEvent(
        new CustomEvent("route:changed", {
            detail: { route: target },
        })
    );
}


/* --------------------------------------------------------
   Rendering
   -------------------------------------------------------- */

export function renderShell() {

    els.authScreen.classList.add("hidden");
    els.shell.classList.remove("hidden");

    els.userName.textContent = state.username || "Member";
    els.userInitials.textContent = initialsOf(state.username);

    if (els.userRoleLabel) {

        els.userRoleLabel.textContent = state.role === "admin"
            ? "Administrator"
            : "Library member";

        els.userRoleLabel.classList.toggle(
            "role-admin",
            state.role === "admin"
        );
    }

    if (loadSidebarCollapsed()) {

        els.shell.classList.add("sidebar-collapsed");
    }

    if (!location.hash) {

        history.replaceState(null, "", "#/chat");
    }

    route();
}


export function showAuth() {

    resetSession();

    els.shell.classList.add("hidden");
    els.shell.classList.remove("sidebar-open", "sidebar-collapsed");
    els.authScreen.classList.remove("hidden");

    showLoginCard();
}


/* --------------------------------------------------------
   Logout
   -------------------------------------------------------- */

async function handleLogout() {

    try {

        await api("/api/logout", {
            method: "POST",
            silent401: true,
        });

    } catch {

        // Session is cleared locally regardless of server result.
    }

    toast("Logged out successfully.", "info");

    history.replaceState(null, "", "#/chat");

    document.dispatchEvent(new CustomEvent("session:logged-out"));
}


/* --------------------------------------------------------
   Init
   -------------------------------------------------------- */

export function initShell() {

    cacheElements();

    // Navigation --------------------------------------------

    document.querySelectorAll(".nav-item[data-route]").forEach(item => {

        item.addEventListener("click", () => {

            location.hash = `#/${item.dataset.route}`;
        });
    });

    // Shortcuts → prefill a chat prompt ----------------------

    document.querySelectorAll(".shortcut-item[data-shortcut]").forEach(item => {

        item.addEventListener("click", () => {

            document.dispatchEvent(
                new CustomEvent("chat:prompt", {
                    detail: item.dataset.shortcut,
                })
            );
        });
    });

    // Sidebar controls ---------------------------------------

    els.collapseButton.addEventListener("click", () => {

        const collapsed = els.shell.classList.toggle("sidebar-collapsed");

        saveSidebarCollapsed(collapsed);
    });

    els.menuButton.addEventListener("click", openSidebar);

    els.scrim.addEventListener("click", closeSidebar);

    // Theme ---------------------------------------------------

    document.getElementById("theme-toggle").addEventListener("click", toggleTheme);

    document.getElementById("theme-toggle-top").addEventListener("click", toggleTheme);

    // Logout + routing ----------------------------------------

    els.logoutButton.addEventListener("click", handleLogout);

    window.addEventListener("hashchange", route);
}
