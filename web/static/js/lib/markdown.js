/* ============================================================
   MARKDOWN — safe mini renderer for assistant messages.
   All input is HTML-escaped before any wrapper markup is
   added, so agent output can never inject HTML.
   ============================================================ */

export function escapeHtml(text) {

    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}


/* --------------------------------------------------------
   Inline rendering
   -------------------------------------------------------- */

function renderInlineMarkdown(raw) {

    let text = escapeHtml(raw);

    const codeStash = [];

    text = text.replace(
        /`([^`]+)`/g,
        (_match, code) => {

            codeStash.push(
                `<code class="inline-code">${code}</code>`
            );

            return `\u0000${codeStash.length - 1}\u0000`;
        }
    );

    text = text.replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );

    text = text.replace(
        /\*\*([^*]+)\*\*/g,
        "<strong>$1</strong>"
    );

    text = text.replace(
        /(^|[\s(>])\*([^*\n]+)\*/g,
        "$1<em>$2</em>"
    );

    text = text.replace(
        /\u0000(\d+)\u0000/g,
        (_match, index) => codeStash[Number(index)]
    );

    return text;
}


/* --------------------------------------------------------
   Table detection
   -------------------------------------------------------- */

const TABLE_ROW = /^\s*\|.*\|\s*$/;

const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;


function isTableHeader(line) {

    return TABLE_ROW.test(line);
}


function isTableSeparator(line) {

    return TABLE_SEPARATOR.test(line);
}


function isTableRow(line) {

    return TABLE_ROW.test(line);
}


function splitTableCells(line) {

    let text = line.trim();

    if (text.startsWith("|")) {

        text = text.slice(1);
    }

    if (text.endsWith("|")) {

        text = text.slice(0, -1);
    }

    return text.split("|").map(cell => cell.trim());
}


function renderTable(lines) {

    const headers = splitTableCells(lines[0]);

    const rows = lines
        .slice(2)
        .map(splitTableCells);

    const head = headers
        .map(cell => `<th scope="col">${renderInlineMarkdown(cell)}</th>`)
        .join("");

    const body = rows
        .map(row => {

            const cells = headers.map((header, i) => {

                const value = row[i] !== undefined ? row[i] : "";

                return `<td data-label="${escapeHtml(header)}">${renderInlineMarkdown(value)}</td>`;
            });

            return `<tr>${cells.join("")}</tr>`;
        })
        .join("");

    return `
        <div class="table-wrapper">
            <table class="responsive-table">
                <thead><tr>${head}</tr></thead>
                <tbody>${body}</tbody>
            </table>
        </div>
    `;
}


/* --------------------------------------------------------
   Code block (with language label + copy button)
   -------------------------------------------------------- */

function renderCodeBlock(language, codeLines) {

    const label = language
        ? escapeHtml(language)
        : "code";

    return `
        <div class="code-block">
            <div class="code-block-head">
                <span class="code-block-lang">${label}</span>
                <button type="button" class="code-copy-button">
                    <svg class="icon icon-sm" aria-hidden="true"><use href="#i-copy"></use></svg>
                    Copy
                </button>
            </div>
            <pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>
        </div>
    `;
}


/* --------------------------------------------------------
   Block-level renderer
   -------------------------------------------------------- */

const UL_ITEM = /^\s*[-*+]\s+(.*)$/;

const OL_ITEM = /^\s*\d+[.)]\s+(.*)$/;

const QUOTE_ITEM = /^\s*>\s?(.*)$/;


export function renderAssistantContent(text) {

    if (!text) {

        return "";
    }

    const lines = String(text)
        .replace(/\r\n/g, "\n")
        .split("\n");

    const output = [];

    let index = 0;

    const flushParagraph = buffer => {

        if (buffer.length > 0) {

            output.push(
                `<p>${buffer.join("<br>")}</p>`
            );

            buffer.length = 0;
        }
    };


    const paragraphBuffer = [];


    while (index < lines.length) {

        const line = lines[index];

        const trimmed = line.trim();

        // Blank line ------------------------------------------

        if (trimmed === "") {

            flushParagraph(paragraphBuffer);

            index++;

            continue;
        }

        // Code fence ------------------------------------------

        if (trimmed.startsWith("```")) {

            flushParagraph(paragraphBuffer);

            const language = trimmed.slice(3).trim();

            const codeLines = [];

            index++;

            while (
                index < lines.length
                && !lines[index].trim().startsWith("```")
            ) {

                codeLines.push(lines[index]);

                index++;
            }

            index++; // skip closing fence (or run off end)

            output.push(
                renderCodeBlock(language, codeLines)
            );

            continue;
        }

        // Table -----------------------------------------------

        if (
            isTableHeader(line)
            && index + 1 < lines.length
            && isTableSeparator(lines[index + 1])
        ) {

            flushParagraph(paragraphBuffer);

            const tableLines = [line, lines[index + 1]];

            index += 2;

            while (
                index < lines.length
                && isTableRow(lines[index])
            ) {

                tableLines.push(lines[index]);

                index++;
            }

            output.push(
                renderTable(tableLines)
            );

            continue;
        }

        // Unordered list --------------------------------------

        if (UL_ITEM.test(line)) {

            flushParagraph(paragraphBuffer);

            const items = [];

            while (
                index < lines.length
                && UL_ITEM.test(lines[index])
            ) {

                items.push(
                    UL_ITEM.exec(lines[index])[1]
                );

                index++;
            }

            output.push(
                `<ul>${items.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`
            );

            continue;
        }

        // Ordered list ----------------------------------------

        if (OL_ITEM.test(line)) {

            flushParagraph(paragraphBuffer);

            const items = [];

            while (
                index < lines.length
                && OL_ITEM.test(lines[index])
            ) {

                items.push(
                    OL_ITEM.exec(lines[index])[1]
                );

                index++;
            }

            output.push(
                `<ol>${items.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ol>`
            );

            continue;
        }

        // Blockquote ------------------------------------------

        if (QUOTE_ITEM.test(line)) {

            flushParagraph(paragraphBuffer);

            const quotes = [];

            while (
                index < lines.length
                && QUOTE_ITEM.test(lines[index])
            ) {

                quotes.push(
                    QUOTE_ITEM.exec(lines[index])[1]
                );

                index++;
            }

            output.push(
                `<blockquote>${quotes.map(q => renderInlineMarkdown(q)).join("<br>")}</blockquote>`
            );

            continue;
        }

        // Paragraph line --------------------------------------

        paragraphBuffer.push(
            renderInlineMarkdown(line)
        );

        index++;
    }

    flushParagraph(paragraphBuffer);

    return output.join("");
}
