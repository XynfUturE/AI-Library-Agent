/* ============================================================
   ICONS — helpers for the inline SVG sprite
   ============================================================ */

export function icon(
    name,
    className = "icon"
) {

    return `<svg class="${className}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}


export function initialsOf(name) {

    if (!name) {

        return "?";
    }

    const parts = String(name)
        .trim()
        .split(/[\s_-]+/)
        .filter(Boolean);

    if (parts.length === 0) {

        return "?";
    }

    if (parts.length === 1) {

        return parts[0].slice(0, 2).toUpperCase();
    }

    return (parts[0][0] + parts[1][0]).toUpperCase();
}
