/* ============================================================
   AUTH VIEW — login, register, demo login, password toggles
   ============================================================ */

import {
    api,
} from "../lib/api.js";

import {
    state,
    savePersistedSession,
} from "../lib/state.js";

import {
    toast,
} from "../lib/toast.js";


const els = {};


function cacheElements() {

    els.loginCard = document.getElementById("login-card");
    els.registerCard = document.getElementById("register-card");
    els.loginForm = document.getElementById("login-form");
    els.registerForm = document.getElementById("register-form");
    els.loginMessage = document.getElementById("login-message");
    els.registerMessage = document.getElementById("register-message");
    els.loginSubmit = document.getElementById("login-submit");
    els.registerSubmit = document.getElementById("register-submit");
    els.showRegisterButton = document.getElementById("show-register-button");
    els.showLoginButton = document.getElementById("show-login-button");
    els.demoLoginButton = document.getElementById("demo-login-button");
}


/* --------------------------------------------------------
   Card switching & inline messages
   -------------------------------------------------------- */

export function showLoginCard() {

    els.loginCard.classList.remove("hidden");
    els.registerCard.classList.add("hidden");

    clearMessage(els.loginMessage);
    clearMessage(els.registerMessage);
}


function showRegisterCard() {

    els.registerCard.classList.remove("hidden");
    els.loginCard.classList.add("hidden");

    clearMessage(els.loginMessage);
    clearMessage(els.registerMessage);
}


function clearMessage(area) {

    area.className = "message-area";
    area.textContent = "";
}


function showMessage(area, message, type) {

    area.className = `message-area ${type}`;
    area.textContent = message;
}


function setBusy(button, busy, busyLabel) {

    if (busy) {

        button.dataset.label = button.textContent;
        button.disabled = true;
        button.textContent = busyLabel;
    } else {

        button.disabled = false;
        button.textContent = button.dataset.label || button.textContent;
    }
}


/* --------------------------------------------------------
   Session handoff
   -------------------------------------------------------- */

function establishSession(data, options = {}) {

    state.sessionId = data.session_id;
    state.userId = data.user_id;
    state.username = data.username;
    state.role = data.role || null;

    savePersistedSession();

    document.dispatchEvent(new CustomEvent("session:established", {
        detail: {
            // The register flow already shows its own success toast,
            // so the global "Welcome back" toast is suppressed there.
            suppressWelcome: Boolean(options.suppressWelcome),
        },
    }));
}


/* --------------------------------------------------------
   Login
   -------------------------------------------------------- */

async function handleLogin(event) {

    event.preventDefault();

    const username = els.loginForm.username.value.trim();
    const password = els.loginForm.password.value;

    if (!username || !password) {

        showMessage(
            els.loginMessage,
            "Please enter your username and password.",
            "error"
        );

        return;
    }

    setBusy(els.loginSubmit, true, "Signing in...");

    try {

        const data = await api("/api/login", {
            method: "POST",
            body: {
                username,
                password,
            },
            auth: false,
            silent401: true,
        });

        if (!data.success) {

            showMessage(
                els.loginMessage,
                data.message || "Login failed.",
                "error"
            );

            return;
        }

        establishSession(data);

    } catch (error) {

        showMessage(
            els.loginMessage,
            error.message,
            "error"
        );

    } finally {

        setBusy(els.loginSubmit, false);
    }
}


/* --------------------------------------------------------
   Demo login
   -------------------------------------------------------- */

async function handleDemoLogin() {

    setBusy(els.demoLoginButton, true, "Starting demo...");

    try {

        const data = await api("/api/demo-login", {
            method: "POST",
            auth: false,
            silent401: true,
        });

        if (!data.success) {

            showMessage(
                els.loginMessage,
                data.message || "Demo login failed.",
                "error"
            );

            return;
        }

        establishSession(data);

    } catch (error) {

        showMessage(
            els.loginMessage,
            error.message,
            "error"
        );

    } finally {

        setBusy(els.demoLoginButton, false);
    }
}


/* --------------------------------------------------------
   Register
   -------------------------------------------------------- */

async function handleRegister(event) {

    event.preventDefault();

    const username = els.registerForm.username.value.trim();
    const email = els.registerForm.email.value.trim();
    const password = els.registerForm.password.value;
    const confirm = els.registerForm.confirmPassword.value;

    // Email is optional (the backend accepts an empty value);
    // only username and password are mandatory.
    if (!username || !password) {

        showMessage(
            els.registerMessage,
            "Please enter a username and password.",
            "error"
        );

        return;
    }

    if (password !== confirm) {

        showMessage(
            els.registerMessage,
            "The passwords do not match.",
            "error"
        );

        return;
    }

    setBusy(els.registerSubmit, true, "Creating account...");

    try {

        const body = {
            username,
            password,
        };

        // Only send the email when the user provided one; the
        // backend treats it as optional either way.
        if (email) {

            body.email = email;
        }

        const data = await api("/api/register", {
            method: "POST",
            body,
            auth: false,
            silent401: true,
        });

        if (!data.success) {

            showMessage(
                els.registerMessage,
                data.message || "Registration failed.",
                "error"
            );

            return;
        }

        toast("Account created successfully.", "success");

        establishSession(data, {
            suppressWelcome: true,
        });

    } catch (error) {

        showMessage(
            els.registerMessage,
            error.message,
            "error"
        );

    } finally {

        setBusy(els.registerSubmit, false);
    }
}


/* --------------------------------------------------------
   Password visibility toggles
   -------------------------------------------------------- */

function initPasswordToggles() {

    document.querySelectorAll(".field-trailing .icon-button").forEach(button => {

        button.addEventListener("click", () => {

            const input = document.getElementById(button.dataset.target);

            if (!input) {

                return;
            }

            const showing = input.type === "text";

            input.type = showing ? "password" : "text";

            button.setAttribute(
                "aria-label",
                showing ? "Show password" : "Hide password"
            );

            button.innerHTML = `
                <svg class="icon icon-sm"><use href="#${showing ? "i-eye" : "i-eye-off"}"></use></svg>
            `;
        });
    });
}


/* --------------------------------------------------------
   Init
   -------------------------------------------------------- */

export function initAuth() {

    cacheElements();

    els.loginForm.addEventListener("submit", handleLogin);
    els.registerForm.addEventListener("submit", handleRegister);
    els.demoLoginButton.addEventListener("click", handleDemoLogin);
    els.showRegisterButton.addEventListener("click", showRegisterCard);
    els.showLoginButton.addEventListener("click", showLoginCard);

    initPasswordToggles();
}
