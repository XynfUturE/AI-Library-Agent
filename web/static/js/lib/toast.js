/* ============================================================
   TOAST — lightweight transient notifications
   ============================================================ */

function createContainer() {

    let container = document.getElementById("toast-container");

    if (!container) {

        container = document.createElement("div");

        container.id = "toast-container";
        container.className = "toast-container";

        document.body.appendChild(container);
    }

    return container;
}


function removeToast(toast) {

    toast.classList.add("leaving");

    toast.addEventListener(
        "animationend",
        () => toast.remove(),
        { once: true }
    );
}


export function toast(
    message,
    type = "info",
    duration = 3600
) {

    const container = createContainer();

    const toast = document.createElement("div");

    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "status");

    const iconName = type === "success"
        ? "i-check"
        : type === "error"
            ? "i-alert"
            : "i-sparkles";

    toast.innerHTML = `
        <svg class="icon icon-sm toast-icon"><use href="#${iconName}"></use></svg>
        <span></span>
    `;

    toast.querySelector("span").textContent = message;

    container.appendChild(toast);

    setTimeout(() => removeToast(toast), duration);
}
