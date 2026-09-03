/* ============================================================
   API — thin fetch wrapper with session header + error type
   ============================================================ */

import {
    state,
    resetSession,
} from "./state.js";

import {
    toast,
} from "./toast.js";


export class ApiError extends Error {

    constructor(message, status) {

        super(message);

        this.name = "ApiError";
        this.status = status;
    }
}


export async function api(
    path,
    {
        method = "GET",
        body,
        auth = true,
        silent401 = false,
    } = {}
) {

    const headers = {};

    if (body !== undefined) {

        headers["Content-Type"] = "application/json";
    }

    if (auth && state.sessionId) {

        headers["X-Session-ID"] = state.sessionId;
    }


    let response;

    try {

        response = await fetch(path, {
            method,
            headers,
            body: body !== undefined ? JSON.stringify(body) : undefined,
        });

    } catch {

        throw new ApiError(
            "Cannot reach the server. Check your connection and try again.",
            0
        );
    }


    let data = null;

    try {

        data = await response.json();

    } catch {

        data = null;
    }


    if (!response.ok) {

        const detail = data && data.detail;

        const message = typeof detail === "string"
            ? detail
            : (data && data.message)
                || `Request failed (${response.status}).`;

        if (response.status === 401 && !silent401) {

            handleSessionExpired();
        }

        throw new ApiError(message, response.status);
    }

    return data;
}


export function handleSessionExpired() {

    if (!state.sessionId) {

        return;
    }

    resetSession();

    toast("Your session has expired. Please log in again.", "error");

    document.dispatchEvent(new CustomEvent("session:expired"));
}
