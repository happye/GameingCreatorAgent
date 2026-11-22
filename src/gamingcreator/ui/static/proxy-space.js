const STATUS_LABELS = {
    valid: "有效",
    missing: "缺件",
    bad_receipt: "坏回执",
    building: "活动构建",
    other: "其他",
};
const SHA256 = /^[a-f0-9]{64}$/;
const selectedSource = new URLSearchParams(location.search).get("source");
const dialog = document.getElementById("reclaim-dialog");
const confirmReclaim = document.getElementById("reclaim-confirm");
const cancelReclaim = document.getElementById("reclaim-cancel");
let selection = null;
let inventoryRequest = 0;

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

function createReclaimButton(item) {
    const button = document.createElement("button");
    button.className = "button secondary compact";
    button.type = "button";
    button.textContent = "回收";
    button.setAttribute("aria-label", `回收代理 ${item.sourceSha256}`);
    button.addEventListener("click", () => {
        selection = item;
        document.getElementById("inventory-result").hidden = true;
        document.getElementById("inventory-error").hidden = true;
        text("reclaim-source", item.sourceSha256);
        text("reclaim-bytes", item.bytes);
        dialog.showModal();
        cancelReclaim.focus();
    });
    return button;
}

async function loadInventory() {
    const request = ++inventoryRequest;
    const response = await fetch("/api/proxy-space");
    const payload = await response.json();
    if (request !== inventoryRequest) return;
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
        if (item.sourceSha256 && item.sourceSha256 === selectedSource) row.dataset.selected = "";
        const cells = [
            item.sourceSha256 || "（活动构建）",
            item.bytes,
            STATUS_LABELS[item.status] || item.status,
            item.reason,
        ];
        for (const value of cells) {
            const cell = document.createElement("td");
            cell.textContent = String(value);
            row.append(cell);
        }
        const action = document.createElement("td");
        if (item.cleanable && SHA256.test(item.sourceSha256) && SHA256.test(item.reclaimToken)) {
            action.append(createReclaimButton(item));
        } else {
            action.textContent = "—";
        }
        row.append(action);
        body.append(row);
    }
}

async function reclaimSelected() {
    if (!selection || confirmReclaim.disabled) return;
    const {sourceSha256, reclaimToken} = selection;
    confirmReclaim.disabled = cancelReclaim.disabled = true;
    try {
        const response = await fetch("/api/reclaim-proxy", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({sourceSha256, reclaimToken}),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.message || "未能回收此代理。");
        if (payload.sourceSha256 !== sourceSha256 || typeof payload.removed !== "boolean"
            || !Number.isSafeInteger(payload.releasedProxyBytes) || payload.releasedProxyBytes < 0) {
            throw new Error("回收结果无法核对，请查看刷新后的清单。");
        }
        text("inventory-result", payload.removed ? `已回收代理，释放 ${payload.releasedProxyBytes} 字节。` : "该代理已不在清单中。");
        document.getElementById("inventory-result").hidden = false;
    } catch (error) {
        showError(error.message || "未能核对回收结果，请查看刷新后的清单。");
    } finally {
        selection = null;
        dialog.close();
        confirmReclaim.disabled = cancelReclaim.disabled = false;
        void loadInventory().catch(() => showError("结果清单读取失败，请刷新页面。"));
    }
}

cancelReclaim.addEventListener("click", () => { selection = null; dialog.close(); });
dialog.addEventListener("cancel", (event) => {
    if (confirmReclaim.disabled) event.preventDefault();
    else selection = null;
});
confirmReclaim.addEventListener("click", () => void reclaimSelected());
loadInventory().catch(() => showError("读取代理空间清单失败。"));
