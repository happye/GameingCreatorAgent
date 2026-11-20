const STATUS_LABELS = {
    valid: "有效",
    missing: "缺件",
    bad_receipt: "坏回执",
    building: "活动构建",
    other: "其他",
};

function text(id, value) {
    const node = document.getElementById(id);
    if (node) {
        node.textContent = String(value);
    }
}

function showError(message) {
    const node = document.getElementById("inventory-error");
    if (!node) {
        return;
    }
    node.hidden = false;
    node.textContent = message;
}

async function loadInventory() {
    const response = await fetch("/api/proxy-space");
    const payload = await response.json();
    if (!response.ok) {
        showError(payload.message || "读取代理空间清单失败。");
        return;
    }
    text("inventory-notice", payload.notice || "只读盘点，未删除。");
    text("total-count", payload.totalCount);
    text("total-bytes", payload.totalBytes);
    const counts = payload.counts || {};
    text("count-valid", counts.valid ?? 0);
    text("count-missing", counts.missing ?? 0);
    text("count-bad_receipt", counts.bad_receipt ?? 0);
    text("count-building", counts.building ?? 0);
    const body = document.querySelector("#inventory-table tbody");
    if (!body) {
        return;
    }
    body.replaceChildren();
    for (const item of payload.items || []) {
        const row = document.createElement("tr");
        const cells = [
            item.sourceSha256 || "（活动构建）",
            item.bytes,
            STATUS_LABELS[item.status] || item.status,
            item.reason,
            item.cleanable ? "是" : "否",
        ];
        for (const value of cells) {
            const cell = document.createElement("td");
            cell.textContent = String(value);
            row.append(cell);
        }
        body.append(row);
    }
}

loadInventory().catch(() => showError("读取代理空间清单失败。"));
