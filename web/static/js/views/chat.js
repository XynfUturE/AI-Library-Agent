/* ============================================================
   CHAT VIEW — welcome screen, streaming messages, tool steps
   ============================================================ */

import {
    api,
    ApiError,
    handleSessionExpired,
} from "../lib/api.js";

import {
    state,
} from "../lib/state.js";

import {
    toast,
} from "../lib/toast.js";

import {
    initialsOf,
} from "../lib/icons.js";

import {
    renderAssistantContent,
    escapeHtml,
} from "../lib/markdown.js";


const els = {};

let streaming = false;

let queuedPrompt = null;

// Active stream cancellation + generation guard.
let streamController = null;

let streamToken = 0;

let lastRunningStep = null;

const rawAssistantText = new WeakMap();


function cacheElements() {

    els.view = document.getElementById("view-chat");
    els.scroll = document.getElementById("chat-scroll");
    els.welcome = document.getElementById("chat-welcome");
    els.welcomeTitle = document.getElementById("welcome-title");
    els.messages = document.getElementById("messages");
    els.form = document.getElementById("chat-form");
    els.input = document.getElementById("chat-input");
    els.sendButton = document.getElementById("send-button");
}


/* --------------------------------------------------------
   Welcome screen
   -------------------------------------------------------- */

export function setWelcomeIdentity() {

    const name = state.username || "";

    els.welcomeTitle.textContent = name
        ? `Hi, ${name} — how can I help?`
        : "Hi, how can I help?";
}


function updateWelcomeVisibility() {

    const empty = els.messages.children.length === 0;

    els.welcome.classList.toggle("hidden", !empty);
}


/* --------------------------------------------------------
   Utilities
   -------------------------------------------------------- */

function timeNow() {

    return new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
    });
}


function isNearBottom() {

    const distance = els.scroll.scrollHeight
        - els.scroll.scrollTop
        - els.scroll.clientHeight;

    return distance < 140;
}


function scrollToBottom() {

    els.scroll.scrollTop = els.scroll.scrollHeight;
}


function resizeInput() {

    els.input.style.height = "auto";

    els.input.style.height = `${Math.min(
        els.input.scrollHeight,
        150
    )}px`;
}


/* --------------------------------------------------------
   Message DOM builders
   -------------------------------------------------------- */

function buildUserRow(text) {

    const row = document.createElement("div");

    row.className = "message-row user";

    row.innerHTML = `
        <div class="avatar user-avatar">${escapeHtml(initialsOf(state.username))}</div>
        <div class="message-body">
            <div class="message-bubble"></div>
            <div class="message-meta">
                <span class="message-time">${timeNow()}</span>
            </div>
        </div>
    `;

    row.querySelector(".message-bubble").textContent = text;

    return row;
}


function buildAssistantRow() {

    const row = document.createElement("div");

    row.className = "message-row assistant";

    row.innerHTML = `
        <div class="avatar assistant-avatar">
            <svg class="icon icon-sm" aria-hidden="true"><use href="#i-sparkles"></use></svg>
        </div>
        <div class="message-body">
            <div class="message-steps"></div>
            <div class="message-bubble hidden"></div>
            <div class="message-meta hidden">
                <span class="message-time">${timeNow()}</span>
                <button type="button" class="message-copy-button">
                    <svg class="icon icon-sm" aria-hidden="true"><use href="#i-copy"></use></svg>
                    Copy
                </button>
            </div>
        </div>
    `;

    return row;
}


function buildErrorRow(message) {

    const row = document.createElement("div");

    row.className = "message-row assistant";

    row.innerHTML = `
        <div class="avatar assistant-avatar">
            <svg class="icon icon-sm" aria-hidden="true"><use href="#i-alert"></use></svg>
        </div>
        <div class="message-body">
            <div class="message-bubble error-bubble"></div>
        </div>
    `;

    row.querySelector(".message-bubble").textContent = message;

    return row;
}


/* --------------------------------------------------------
   Tool step cards
   -------------------------------------------------------- */

function addToolStep(event) {

    lastRunningStep = null;

    const args = Array.isArray(event.args) ? event.args : [];

    const detailItems = args
        .map(arg => `<code><b>${escapeHtml(arg.name)}</b>: ${escapeHtml(arg.value)}</code>`)
        .join("");

    const step = document.createElement("div");

    step.className = "tool-step running";

    step.innerHTML = `
        <button type="button" class="tool-step-head">
            <span class="tool-step-icon">
                <svg class="icon icon-sm spinner" aria-hidden="true"><use href="#i-loader"></use></svg>
            </span>
            <span class="tool-step-label"></span>
            ${detailItems ? `<svg class="icon icon-sm tool-step-chevron" aria-hidden="true"><use href="#i-chevron-right"></use></svg>` : ""}
        </button>
        ${detailItems ? `<div class="tool-step-detail" hidden>${detailItems}</div>` : ""}
    `;

    step.querySelector(".tool-step-label").textContent = event.message || "Working...";

    step.querySelector(".tool-step-head").addEventListener("click", () => {

        const detail = step.querySelector(".tool-step-detail");

        if (!detail) {

            return;
        }

        const expanded = step.classList.toggle("expanded");

        detail.hidden = !expanded;
    });

    lastRunningStep = step;

    return step;
}


function completeToolStep(event, failed) {

    const step = (event.tool && findStepByTool(event.tool))
        || lastRunningStep;

    if (!step) {

        return;
    }

    step.classList.remove("running");
    step.classList.add(failed ? "failed" : "done");

    step.querySelector(".tool-step-icon").innerHTML = `
        <svg class="icon icon-sm" aria-hidden="true"><use href="#${failed ? "i-x" : "i-check"}"></use></svg>
    `;

    if (failed && event.message) {

        let detail = step.querySelector(".tool-step-detail");

        if (!detail) {

            detail = document.createElement("div");

            detail.className = "tool-step-detail";

            step.appendChild(detail);
        }

        detail.hidden = false;

        detail.insertAdjacentHTML(
            "beforeend",
            `<code>${escapeHtml(event.message)}</code>`
        );
    }

    lastRunningStep = null;
}


function findStepByTool(toolName) {

    const steps = els.messages.querySelectorAll(".tool-step.running");

    for (const step of steps) {

        if (step.dataset.tool === toolName) {

            return step;
        }
    }

    return null;
}


/* --------------------------------------------------------
   SSE handling
   -------------------------------------------------------- */

function handleAgentEvent(event, context) {

    switch (event.type) {

        case "agent_start":

            if (context.statusLabel) {

                context.statusLabel.textContent = "Thinking...";
            }

            break;

        case "tool_start": {

            if (context.statusRow) {

                context.statusRow.remove();
                context.statusRow = null;
            }

            const step = addToolStep(event);

            step.dataset.tool = event.tool || "";

            context.row
                .querySelector(".message-steps")
                .appendChild(step);

            scrollToBottom();

            break;
        }

        case "tool_result":

            completeToolStep(event, false);

            break;

        case "tool_error":

            completeToolStep(event, true);

            break;

        case "final":

            finishAssistantMessage(context, event.message || "");

            break;

        case "error":

            removeStatusRow(context);

            // If nothing was rendered yet (no steps, no content),
            // drop the empty assistant row entirely.

            const hasSteps = context.row.querySelector(".tool-step");

            if (!hasSteps) {

                context.row.remove();
            }

            els.messages.appendChild(
                buildErrorRow(event.message || "Something went wrong.")
            );

            scrollToBottom();

            break;

        default:

            break;
    }
}


function removeStatusRow(context) {

    if (context.statusRow) {

        context.statusRow.remove();

        context.statusRow = null;
    }
}


function finishAssistantMessage(context, markdown) {

    removeStatusRow(context);

    const bubble = context.row.querySelector(".message-bubble");

    bubble.classList.remove("hidden");
    bubble.innerHTML = renderAssistantContent(markdown);

    rawAssistantText.set(bubble, markdown);

    context.row.querySelector(".message-meta").classList.remove("hidden");

    scrollToBottom();
}


/* --------------------------------------------------------
   Streaming request
   -------------------------------------------------------- */

export async function sendStreamingMessage(text) {

    const message = text.trim();

    if (!message || streaming || !state.sessionId) {

        return;
    }

    streaming = true;

    els.sendButton.disabled = true;

    const controller = new AbortController();

    streamController = controller;

    const token = ++streamToken;

    els.welcome.classList.add("hidden");

    const wasNearBottom = isNearBottom();

    els.messages.appendChild(buildUserRow(message));

    const row = buildAssistantRow();

    els.messages.appendChild(row);

    // Transient status row shown until the first tool call
    // or the final answer arrives.

    const statusRow = document.createElement("div");

    statusRow.className = "message-row assistant";

    statusRow.innerHTML = `
        <div class="avatar assistant-avatar">
            <svg class="icon icon-sm spinner" aria-hidden="true"><use href="#i-loader"></use></svg>
        </div>
        <div class="message-body">
            <div class="message-bubble status-bubble">Thinking...</div>
        </div>
    `;

    row.querySelector(".message-steps").appendChild(statusRow);

    const context = {
        row,
        statusRow,
        statusLabel: statusRow.querySelector(".status-bubble"),
    };

    if (wasNearBottom) {

        scrollToBottom();
    }


    try {

        const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Session-ID": state.sessionId,
            },
            body: JSON.stringify({ message }),
            signal: controller.signal,
        });


        if (!response.ok) {

            let detail = `Request failed (${response.status}).`;

            try {

                const data = await response.json();

                if (typeof data.detail === "string") {

                    detail = data.detail;
                }

            } catch {

                // keep default message
            }

            if (response.status === 401) {

                handleSessionExpired();

                return;
            }

            throw new ApiError(detail, response.status);
        }


        const reader = response.body.getReader();

        const decoder = new TextDecoder();

        let buffer = "";


        while (true) {

            const { value, done } = await reader.read();

            if (done) {

                break;
            }

            buffer += decoder.decode(value, { stream: true });

            let boundary;

            while ((boundary = buffer.indexOf("\n\n")) !== -1) {

                const chunk = buffer.slice(0, boundary);

                buffer = buffer.slice(boundary + 2);

                for (const line of chunk.split("\n")) {

                    if (!line.startsWith("data: ")) {

                        continue;
                    }

                    try {

                        handleAgentEvent(
                            JSON.parse(line.slice(6)),
                            context
                        );

                    } catch {

                        // Malformed event line is ignored.
                    }
                }
            }
        }


        // No final event arrived (connection closed early).

        if (!context.row.querySelector(".message-bubble:not(.hidden)")) {

            finishAssistantMessage(
                context,
                "*The connection was interrupted. Please try again.*"
            );
        }

    } catch (error) {

        // The stream was cancelled by a UI reset (logout,
        // session switch...): nothing to render.
        if (error?.name === "AbortError" || token !== streamToken) {

            return;
        }

        removeStatusRow(context);

        if (!context.row.querySelector(".tool-step")) {

            context.row.remove();
        }

        els.messages.appendChild(
            buildErrorRow(
                error.message || "The AI service could not complete your request."
            )
        );

        scrollToBottom();

    } finally {

        if (streamController === controller) {

            streamController = null;
        }

        // Only the most recent stream may touch shared UI state.
        if (token === streamToken) {

            streaming = false;

            els.sendButton.disabled = false;

            els.input.focus();

            els.scroll.scrollTop = els.scroll.scrollHeight;
        }
    }
}


/* --------------------------------------------------------
   Copy handling (delegated)
   -------------------------------------------------------- */

async function copyText(text, button) {

    try {

        await navigator.clipboard.writeText(text);

        const label = button.querySelector("span");

        if (label) {

            const original = label.textContent;

            label.textContent = "Copied";

            setTimeout(() => {

                label.textContent = original;
            }, 1500);
        }

    } catch {

        toast("Copy failed. Please copy manually.", "error");
    }
}


function handleDelegatedClick(event) {

    const codeCopy = event.target.closest(".code-copy-button");

    if (codeCopy) {

        const code = codeCopy
            .closest(".code-block")
            ?.querySelector("pre code");

        if (code) {

            copyText(code.textContent, codeCopy);
        }

        return;
    }

    const messageCopy = event.target.closest(".message-copy-button");

    if (messageCopy) {

        const bubble = messageCopy
            .closest(".message-row")
            ?.querySelector(".message-bubble");

        const raw = bubble
            ? rawAssistantText.get(bubble)
            : null;

        if (raw !== null && raw !== undefined) {

            copyText(raw, messageCopy);
        }
    }
}


/* --------------------------------------------------------
   Prompt queue (shortcuts, My Shelf actions)
   -------------------------------------------------------- */

export function queuePrompt(prompt) {

    if (!state.sessionId) {

        return;
    }

    if (streaming) {

        queuedPrompt = prompt;

        toast("Your request will be sent after the current reply.", "info");

        return;
    }

    sendStreamingMessage(prompt);
}


function flushQueuedPrompt() {

    if (queuedPrompt && !streaming) {

        const prompt = queuedPrompt;

        queuedPrompt = null;

        sendStreamingMessage(prompt);
    }
}


/* --------------------------------------------------------
   Reset & init
   -------------------------------------------------------- */

export function resetChatUI() {

    // Cancel any in-flight stream and invalidate its callbacks.
    streamToken += 1;

    if (streamController) {

        streamController.abort();

        streamController = null;
    }

    els.messages.innerHTML = "";

    streaming = false;

    queuedPrompt = null;

    lastRunningStep = null;

    els.input.value = "";

    resizeInput();

    updateWelcomeVisibility();

    els.scroll.scrollTop = 0;
}


export function initChat() {

    cacheElements();

    setWelcomeIdentity();

    // Composer ----------------------------------------------

    els.form.addEventListener("submit", event => {

        event.preventDefault();

        const message = els.input.value;

        if (streaming) {

            queuePrompt(message);

            els.input.value = "";

            resizeInput();

            return;
        }

        els.input.value = "";

        resizeInput();

        sendStreamingMessage(message);
    });

    els.input.addEventListener("input", resizeInput);

    els.input.addEventListener("keydown", event => {

        if (event.key === "Enter" && !event.shiftKey) {

            event.preventDefault();

            els.form.requestSubmit();
        }
    });

    // Suggestion cards ---------------------------------------

    document.querySelectorAll(".suggestion-card[data-prompt]").forEach(card => {

        card.addEventListener("click", () => {

            queuePrompt(card.dataset.prompt);
        });
    });

    // Copy delegation ----------------------------------------

    els.messages.addEventListener("click", handleDelegatedClick);

    // External prompts ---------------------------------------

    document.addEventListener("chat:prompt", event => {

        if (location.hash !== "#/chat") {

            location.hash = "#/chat";
        }

        queuePrompt(event.detail);
    });

    document.addEventListener("route:changed", event => {

        if (event.detail.route === "chat") {

            flushQueuedPrompt();

            if (!streaming) {

                els.input.focus();
            }
        }
    });
}
