// P019: one sentence → recognized brief fields (local rules, no model); applied only on click.
import {h} from "../vendor/preact.module.js";
import {useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api} from "./api.js";
const html = htm.bind(h);
const split = (text) => text.split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean);

export function patchFor(fields, draft) {
    const patch = {};
    for (const key of ["game", "contentType", "platform", "objective", "audience"]) if (fields[key] != null) patch[key] = String(fields[key]);
    if (fields.targetDuration != null) patch.targetDuration = String(fields.targetDuration);
    for (const key of ["mandatoryTopics", "exclude"]) {
        if (fields[key]?.length) patch[key] = [...new Set([...split(draft[key] || ""), ...fields[key]])].join(", ");
    }
    return patch;
}

// Game names from recording file names ("漫画群星：大集结 - TapTap.mp4" -> "漫画群星：大集结").
const gameNames = (runs = []) => [...new Set(runs.map((r) => (r.sourceName || "").replace(/\.[^.]+$/, "").split(/\s+-\s+/)[0].trim()).filter((n) => n.length >= 2))];

export function BriefSentence({draft, update, runs = []}) {
    const [text, setText] = useState(""), [result, setResult] = useState(null), [message, setMessage] = useState("");
    const parse = async () => {
        if (!text.trim()) return;
        try {
            const parsed = await api("/api/creation/brief-sentence", {}, {body: {text: text.trim(), games: gameNames(runs)}});
            setResult(parsed);
            setMessage(parsed.recognized.length ? `识别到：${parsed.recognized.join("；")}。其余保持不变。` : "没有识别到时长、类型、平台等，只会把这句话作为创作目标。");
        } catch (error) { setResult(null); setMessage(`未能解析：${error.message}`); }
    };
    const apply = () => { update(patchFor(result.fields, draft)); setResult(null); setMessage("已填入下方需求，可继续修改后生成方案。"); };
    return html`<div class="field brief-sentence"><div class="k">一句话需求（本机规则，不调用模型）</div>
        <textarea class="input" rows="2" maxlength="500" aria-label="一句话需求" placeholder="例如：给新玩家做个《游戏名》1分钟玩法展示，发B站，要有Boss战"
            value=${text} onInput=${(e) => { setText(e.currentTarget.value); setResult(null); setMessage(""); }}></textarea>
        <div class="actions-row"><button type="button" class="btn ghost" disabled=${!text.trim()} onClick=${parse}>解析</button>
            ${result ? html`<button type="button" class="btn" onClick=${apply}>填入需求</button>` : null}</div>
        <p class="hint" role="status" aria-label="一句话需求状态">${message}</p>
    </div>`;
}
