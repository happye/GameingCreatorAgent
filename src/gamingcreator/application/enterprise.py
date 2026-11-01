"""Enterprise basics on one machine: team roles, brand glossary checks and package review.

This is a local team model (master plan §41), not an account system: names are labels chosen
by the team, there is no login, and nothing is sent anywhere. Rules are still enforced: only
reviewers/owners approve, nobody approves their own submission, forbidden brand terms block
approval, and every review step is kept in an append-only history.
"""

from typing import Any

ROLES = {"owner": "负责人", "editor": "编辑", "reviewer": "审核", "viewer": "只读"}
PERMISSIONS = {
    "submit": {"owner", "editor"},
    "approve": {"owner", "reviewer"},
    "reject": {"owner", "reviewer"},
    "edit_team": {"owner"},
}


def validate_team(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"members", "brandTerms", "reviewRequired"}:
        raise ValueError("团队设置字段无效。")
    members = value.get("members", [])
    if not isinstance(members, list) or not members or len(members) > 200:
        raise ValueError("至少需要一名成员，最多200名。")
    names = []
    for member in members:
        if (
            not isinstance(member, dict)
            or set(member) != {"name", "role"}
            or not isinstance(member["name"], str)
            or not member["name"].strip()
            or len(member["name"]) > 50
            or member["role"] not in ROLES
        ):
            raise ValueError("成员需要1–50字的名字和有效角色。")
        names.append(member["name"].strip())
    if len(set(names)) != len(names):
        raise ValueError("成员名字不能重复。")
    if not any(m["role"] == "owner" for m in members):
        raise ValueError("团队至少需要一名负责人。")
    terms = value.get("brandTerms", {"required": [], "forbidden": []})
    if not isinstance(terms, dict) or set(terms) != {"required", "forbidden"}:
        raise ValueError("品牌词库需要 required 与 forbidden 两组。")
    for key in ("required", "forbidden"):
        items = terms[key]
        if not isinstance(items, list) or any(
            not isinstance(t, str) or not t.strip() or len(t) > 50 for t in items
        ):
            raise ValueError("品牌词需为1–50字的文本。")
    review = value.get("reviewRequired", False)
    if type(review) is not bool:
        raise ValueError("reviewRequired 需为 true/false。")
    return {
        "members": [{"name": m["name"].strip(), "role": m["role"]} for m in members],
        "brandTerms": {k: [t.strip() for t in terms[k]] for k in ("required", "forbidden")},
        "reviewRequired": review,
    }


def role_of(team: dict[str, Any], actor: str) -> str:
    member = next((m for m in team["members"] if m["name"] == actor), None)
    if member is None:
        raise PermissionError(f"“{actor}”不是团队成员。")
    return str(member["role"])


def check_brand(team: dict[str, Any], texts: dict[str, str]) -> list[str]:
    """Problems with the publication texts against the brand glossary (empty = fine)."""
    combined = "\n".join(texts.values()).casefold()
    issues = [
        f"缺少必须出现的品牌词“{t}”"
        for t in team["brandTerms"]["required"]
        if t.casefold() not in combined
    ]
    for term in team["brandTerms"]["forbidden"]:
        for field, text in texts.items():
            if term.casefold() in text.casefold():
                issues.append(f"{field}含禁用词“{term}”")
    return issues


def publish_blockers(
    team: dict[str, Any] | None, record: dict[str, Any] | None, brand_issues: list[str]
) -> list[str]:
    """Why an approved package may still not be published under the team's current settings.

    An approval is checked again at publishing time: a later glossary change or a reviewer who
    lost the role makes the old approval insufficient.
    """
    if team is None or not team["reviewRequired"]:
        return []
    if record is None or record.get("state") != "approved":
        return ["团队要求审核通过后才能发布，这个发布包尚未审核通过。"]
    approver = record["events"][-1]["actor"] if record.get("events") else ""
    blockers = []
    members = {m["name"]: m["role"] for m in team["members"]}
    if members.get(str(approver)) not in PERMISSIONS["approve"]:
        blockers.append("批准人已不再是审核员，请重新提交审核。")
    if brand_issues:
        blockers.append("团队品牌词已更新，请重新提交审核：" + "；".join(brand_issues))
    return blockers


def apply_review(
    team: dict[str, Any],
    record: dict[str, Any] | None,
    actor: str,
    action: str,
    comment: str,
    brand_issues: list[str],
    at: str,
) -> dict[str, Any]:
    if action not in ("submit", "approve", "reject"):
        raise ValueError("审核操作只能是提交、通过或驳回。")
    if not isinstance(comment, str) or len(comment) > 1000:
        raise ValueError("意见最多1000字。")
    role = role_of(team, actor)
    if role not in PERMISSIONS[action]:
        raise PermissionError(f"{ROLES[role]}不能执行“{action}”。")
    state = record["state"] if record else None
    if action == "submit":
        if state == "pending":
            raise ValueError("已在审核中。")
        record = {
            "state": "pending",
            "submittedBy": actor,
            "events": list(record["events"]) if record else [],
        }
    else:
        if record is None or state != "pending":
            raise ValueError("只有审核中的发布包可以通过或驳回。")
        if actor == record["submittedBy"]:
            raise PermissionError("不能审核自己提交的发布包。")
        if action == "approve" and brand_issues:
            raise ValueError("品牌词检查未通过：" + "；".join(brand_issues))
        if action == "reject" and not comment.strip():
            raise ValueError("驳回需要写明原因。")
        record = {
            **record,
            "state": "approved" if action == "approve" else "rejected",
            "events": list(record["events"]),
        }
    record["events"].append(
        {
            "actor": actor,
            "role": role,
            "action": action,
            "comment": comment.strip(),
            "brandIssues": brand_issues,
            "at": at,
        }
    )
    return record
