/* ============================================================
   APP ENTRY — boot, session restore, global wiring
   ============================================================ */

import {
    api,
} from "./lib/api.js";

import {
    state,
    initTheme,
    resetSession,
    savePersistedSession,
    loadPersistedSession,
} from "./lib/state.js";

import {
    toast,
} from "./lib/toast.js";

import {
    initAuth,
} from "./views/auth.js";

import {
    initShell,
    renderShell,
    showAuth,
} from "./views/shell.js";

import {
    initChat,
    resetChatUI,
    setWelcomeIdentity,
} from "./views/chat.js";

import {
    initShelf,
} from "./views/shelf.js";

import {
    initCatalog,
} from "./views/catalog.js";


initTheme();

initAuth();

initShell();

initChat();

initShelf();

initCatalog();


/* --------------------------------------------------------
   Global session lifecycle
   -------------------------------------------------------- */

document.addEventListener("session:established", event => {

    renderShell();
    setWelcomeIdentity();
    resetChatUI();

    // The register flow toasts its own success message, so avoid
    // stacking a second generic "Welcome back" toast on top of it.
    const suppressWelcome = event.detail && event.detail.suppressWelcome;

    if (!suppressWelcome) {

        toast(`Welcome back, ${state.username || "reader"}!`, "success");
    }
});


document.addEventListener("session:logged-out", () => {

    showAuth();
    resetChatUI();
});


document.addEventListener("session:expired", () => {

    showAuth();
    resetChatUI();
});


/* --------------------------------------------------------
   Boot: restore a persisted session after page refresh
   -------------------------------------------------------- */

(async function boot() {

    const saved = loadPersistedSession();

    if (!saved) {

        return;
    }

    state.sessionId = saved.sessionId;
    state.username = saved.username || null;

    try {

        const check = await api("/api/session/check", {
            silent401: true,
        });

        state.userId = check.user_id;
        state.username = check.username;
        state.role = check.role || null;

        savePersistedSession();

        renderShell();
        setWelcomeIdentity();
        resetChatUI();

        toast(`Welcome back, ${check.username}!`, "success");

    } catch {

        resetSession();
    }
})();
