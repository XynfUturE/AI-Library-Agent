/* ============================================================
   STATE — app state, theme handling, session persistence
   ============================================================ */

export const state = {
    sessionId: null,
    userId: null,
    username: null,
    role: null,
};

const SESSION_KEY = "ai-library-session";
const THEME_KEY = "ai-library-theme";
const SIDEBAR_KEY = "ai-library-sidebar-collapsed";


/* --------------------------------------------------------
   Theme
   -------------------------------------------------------- */

export function currentTheme() {

    return document.documentElement.getAttribute("data-theme")
        || "light";
}


export function applyTheme(theme) {

    document.documentElement.setAttribute("data-theme", theme);

    localStorage.setItem(THEME_KEY, theme);

    const href = theme === "dark" ? "#i-sun" : "#i-moon";

    for (const id of ["theme-toggle-icon", "theme-toggle-icon-top"]) {

        const use = document.getElementById(id);

        if (use) {

            use.setAttribute("href", href);
        }
    }

    const label = document.getElementById("theme-label");

    if (label) {

        label.textContent = theme === "dark" ? "Dark theme" : "Light theme";
    }
}


export function toggleTheme() {

    applyTheme(currentTheme() === "dark" ? "light" : "dark");
}


export function initTheme() {

    const stored = localStorage.getItem(THEME_KEY);

    const theme = (stored === "dark" || stored === "light")
        ? stored
        : (window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light");

    applyTheme(theme);
}


/* --------------------------------------------------------
   Sidebar preference
   -------------------------------------------------------- */

export function loadSidebarCollapsed() {

    return localStorage.getItem(SIDEBAR_KEY) === "1";
}


export function saveSidebarCollapsed(collapsed) {

    localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
}


/* --------------------------------------------------------
   Session persistence (survives page refresh in the tab)
   --------------------------------------------------------
   sessionStorage (not localStorage) is used on purpose: the
   session id is a bearer token for the API, and keeping it in
   sessionStorage scopes it to the current tab and drops it as
   soon as the tab is closed, reducing the standing XSS / shared-
   machine exposure surface. */

const sessionStore = window.sessionStorage;

export function savePersistedSession() {

    if (!state.sessionId) {

        return;
    }

    sessionStore.setItem(
        SESSION_KEY,
        JSON.stringify({
            sessionId: state.sessionId,
            username: state.username,
        })
    );
}


export function loadPersistedSession() {

    try {

        const raw = sessionStore.getItem(SESSION_KEY);

        if (!raw) {

            return null;
        }

        const saved = JSON.parse(raw);

        if (!saved || typeof saved.sessionId !== "string") {

            return null;
        }

        return saved;

    } catch {

        return null;
    }
}


export function clearPersistedSession() {

    sessionStore.removeItem(SESSION_KEY);
}


/* --------------------------------------------------------
   Session reset
   -------------------------------------------------------- */

export function resetSession() {

    state.sessionId = null;
    state.userId = null;
    state.username = null;
    state.role = null;

    clearPersistedSession();
}
