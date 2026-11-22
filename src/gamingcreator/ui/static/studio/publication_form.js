// Client checks for the publish form title, description and tags.
// Keep the wording aligned with domain/publication.py so the same field is named.

const CONTROL = /\p{Cc}/u;
const MULTILINE_OK = /[\r\n\t]/;

function problem(text, minimum, maximum, multiline) {
    if (typeof text !== "string") return "格式无效";
    if ([...text].length > maximum) return `不能超过 ${maximum} 字`;
    if (minimum && (text.length < minimum || !text.trim())) return "不能为空";
    if ([...text].some((ch) => CONTROL.test(ch) && !(multiline && MULTILINE_OK.test(ch)))) {
        return "包含无效字符";
    }
    return "";
}

export function publicationFieldErrors({title, description, tags}) {
    const errors = {};
    const titleProblem = problem(title, 1, 200, false);
    if (titleProblem) errors.title = `标题${titleProblem}。`;
    const descriptionProblem = problem(description, 0, 5000, true);
    if (descriptionProblem) errors.description = `简介${descriptionProblem}。`;
    if (!Array.isArray(tags)) {
        errors.tags = "标签格式无效。";
        return errors;
    }
    if (tags.length > 20) errors.tags = "标签不能超过 20 个。";
    else if (tags.length !== new Set(tags).size) errors.tags = "标签不能重复。";
    else {
        for (const tag of tags) {
            const tagProblem = problem(tag, 1, 50, false);
            if (!tagProblem) continue;
            errors.tags = tagProblem === "不能超过 50 字" ? "单个标签不能超过 50 字。" : `标签${tagProblem}。`;
            break;
        }
    }
    return errors;
}

export function publicationErrorFields(message) {
    const text = String(message || "").replace(/^无法提交：/, "").trim();
    if (!text || /ValueError|Invalid local publication|Traceback/i.test(text) || !/[\u4e00-\u9fff]/.test(text)) {
        return {message: "无法保存发布信息。", fields: {}};
    }
    const names = {标题: "title", 简介: "description", 标签: "tags", 封面帧: "coverFrame"};
    for (const [label, key] of Object.entries(names)) {
        if (text.startsWith(label)) return {message: "", fields: {[key]: text}};
    }
    return {message: text, fields: {}};
}
