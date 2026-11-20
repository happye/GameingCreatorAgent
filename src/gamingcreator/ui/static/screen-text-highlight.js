"use strict";

// 屏幕文字高亮：按字素切开，用 NFKC 和小写做匹配，始终回写原文，不用规范化后的下标去切原文。
(function (root) {
    function screenTextKey(text) {
        return String(text || "").normalize("NFKC").toLocaleLowerCase("und");
    }

    function graphemes(text) {
        const value = String(text || "");
        if (typeof Intl !== "undefined" && Intl.Segmenter) {
            return [...new Intl.Segmenter("und", { granularity: "grapheme" }).segment(value)].map((item) => item.segment);
        }
        return [...value];
    }

    function screenTextHighlightRanges(text, query) {
        const value = String(text || "");
        const needle = screenTextKey(query).trim();
        const clusters = graphemes(value);
        if (!needle || !clusters.length) return [{ value, hit: false }];
        const pieces = [];
        const owners = [];
        clusters.forEach((cluster, index) => {
            const key = screenTextKey(cluster);
            pieces.push(key);
            for (let i = 0; i < key.length; i += 1) owners.push(index);
        });
        const haystack = pieces.join("");
        const hits = clusters.map(() => false);
        let from = 0;
        while (from <= haystack.length - needle.length) {
            const at = haystack.indexOf(needle, from);
            if (at < 0) break;
            const first = owners[at];
            const last = owners[at + needle.length - 1];
            for (let index = first; index <= last; index += 1) hits[index] = true;
            from = at + needle.length;
        }
        const parts = [];
        for (const [index, cluster] of clusters.entries()) {
            if (parts.length && parts[parts.length - 1].hit === hits[index]) parts[parts.length - 1].value += cluster;
            else parts.push({ value: cluster, hit: hits[index] });
        }
        return parts;
    }

    function appendScreenTextHighlight(container, text, query) {
        const parts = screenTextHighlightRanges(text, query);
        const nodes = parts.map((part) => {
            if (!part.hit) return container.ownerDocument.createTextNode(part.value);
            const mark = container.ownerDocument.createElement("mark");
            mark.className = "screen-text-hit";
            mark.textContent = part.value;
            return mark;
        });
        container.replaceChildren(...nodes);
    }

    const api = { screenTextKey, graphemes, screenTextHighlightRanges, appendScreenTextHighlight };
    if (typeof module === "object" && module.exports) module.exports = api;
    root.ScreenTextHighlight = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
