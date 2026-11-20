"""Recent clip snapshots are opt-in recovery, with no submit/model side effects."""

import pytest

# ruff: noqa: F811
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401
from test_studio_narration_tools_browser import studio_plan  # noqa: F401
from test_studio_works_browser import new_work


def mount(studio, work="work-a"):
    page = studio.page
    page.evaluate(
        """async ({root, plan, work}) => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {useClipEditor} = await import('/assets/studio/clipedit.js');
        window.draftModule = await import('/assets/studio/clip_drafts.js');
        window.draftHost?.remove();
        window.draftHost = document.body.appendChild(document.createElement('div'));
        function Harness() { window.ce = useClipEditor('artifacts/project', work); return h('span'); }
        render(h(Harness), window.draftHost);
        await new Promise(r => setTimeout(r, 40));
        await window.ce.load(root, plan, 'plan');
    }""",
        {"root": studio.root, "plan": studio.plan_id, "work": work},
    )
    page.wait_for_function("() => ce.status === 'ready' && (ce.drafts.ready || !ce.drafts.key)")


def backup(studio):
    studio.page.evaluate("ce.ops.speed(ce.clips[0].clipId, 1, 2)")
    studio.page.wait_for_function("() => ce.drafts.payload?.rows[0].speed.denominator === 2")


def test_refresh_manual_restore_five_fields_and_work_isolation(studio_plan):
    s = studio_plan
    mount(s)
    before = list(s.posts)
    backup(s)
    rows = s.page.evaluate("draftModule.clipRows(ce.clips)")
    s.page.reload()
    mount(s)
    assert not s.page.evaluate("ce.dirty")
    s.page.evaluate("ce.restoreDraft(() => true)")
    s.page.wait_for_function("() => ce.dirty")
    assert s.page.evaluate("draftModule.clipRows(ce.clips)") == rows
    mount(s, "work-b")
    assert s.page.evaluate("ce.drafts.payload") is None
    assert s.posts == before


@pytest.mark.parametrize(
    "damage",
    ["hash", "receipt", "empty", "duplicate", "unknown", "bounds", "speed", "zero", "transition"],
)
def test_invalid_snapshot_rejected_as_a_whole(studio_plan, damage):
    s = studio_plan
    mount(s)
    backup(s)
    result = s.page.evaluate(
        """async damage => {
        const m = draftModule, payload = structuredClone(ce.drafts.payload), row = payload.rows[0];
        if (damage === 'receipt') payload.expectedParentReceiptSha256 = 'bad';
        if (damage === 'empty') payload.rows = [];
        if (damage === 'duplicate') payload.rows.push(structuredClone(row));
        if (damage === 'unknown') row.clipId = 'unknown';
        if (damage === 'bounds') row.startUs = -1;
        if (damage === 'speed') row.speed = {numerator: 2, denominator: 2};
        if (damage === 'zero') row.endUs = row.startUs + 1;
        if (damage === 'transition') row.transitionIn = {type: 'crossfade', frames: 1};
        const raw = JSON.stringify({payload, sha256: damage === 'hash' ? 'bad' : await m.payloadHash(payload)});
        localStorage.setItem(ce.drafts.key, raw);
        try { await m.readSnapshot(localStorage, ce.drafts.key, ce.editor,
            [(await import('/assets/studio/clipedit.js')).SPEEDS,
             (await import('/assets/studio/preview.js')).clipFrames,
             (await import('/assets/studio/clipedit.js')).transitionProblem]); return false; }
        catch { return localStorage.getItem(ce.drafts.key) === raw; }
    }""",
        damage,
    )
    assert result


def test_unsupported_edits_freeze_snapshot_and_dirty_cancel(studio_plan):
    s = studio_plan
    mount(s)
    backup(s)
    original = s.page.evaluate("ce.drafts.payload.rows")
    s.page.evaluate("ce.ops.mix({sourceGainDb: -8})")
    s.page.wait_for_function("() => ce.drafts.payload?.partial")
    assert s.page.evaluate("ce.drafts.payload.rows") == original
    before = s.page.evaluate(
        "JSON.stringify({audio: ce.audio, clips: ce.clips, stored: localStorage.getItem(ce.drafts.key)})"
    )
    s.page.evaluate("ce.restoreDraft(() => false)")
    assert (
        s.page.evaluate(
            "JSON.stringify({audio: ce.audio, clips: ce.clips, stored: localStorage.getItem(ce.drafts.key)})"
        )
        == before
    )
    s.page.evaluate("ce.ops.undo()")
    s.page.wait_for_function("() => ce.drafts.payload && !ce.drafts.payload.partial")


def test_failed_save_preserves_snapshot_success_clears_parent(studio_plan):
    s = studio_plan
    mount(s)
    backup(s)
    key = s.page.evaluate("ce.drafts.key")
    s.page.evaluate("ce.save(async () => ({status: 'failed'})).catch(() => {})")
    s.page.wait_for_function("() => localStorage.getItem(ce.drafts.key) !== null")
    assert s.page.evaluate("localStorage.getItem(ce.drafts.key)")
    # Frontend completion contract: saved_plan's fake manifest cannot execute revisions.
    editor = s.page.evaluate("ce.editor")
    target = "draft-completed-version"
    editor["parentJobId"] = target
    pending = []
    s.page.route("**/api/creation/revisions", lambda route: route.fulfill(json={"jobId": target}))
    s.page.route(f"**/api/creation/jobs/{target}/edit?*", lambda route: pending.append(route))
    s.page.evaluate("void ce.save(async id => ({jobId: id, status: 'completed'}))")
    s.page.wait_for_function("() => ce.status === 'loading'")
    s.page.wait_for_timeout(400)
    assert s.page.evaluate("key => localStorage.getItem(key)", key) is None
    assert pending
    pending[0].fulfill(json=editor)
    s.page.wait_for_function("() => !ce.dirty")
    assert s.page.evaluate("key => localStorage.getItem(key)", key) is None


def test_parent_source_and_audio_are_rebuilt_from_parent_only(studio_plan):
    mount(studio_plan)
    assert studio_plan.page.evaluate("""async () => {
        const {SPEEDS, transitionProblem} = await import('/assets/studio/clipedit.js');
        const {clipFrames} = await import('/assets/studio/preview.js');
        const parent = structuredClone(ce.editor);
        parent.clips[0].sourcePath = 'parent-private-path';
        parent.clips[0].candidateId = 'already-saved-replacement';
        parent.audioMix = {bgm: {trackId: 'saved-music'}, sourceGainDb: -4};
        const rows = draftModule.clipRows(ce.clips);
        rows[0].sourcePath = 'injected'; rows[0].speed.extra = 'injected';
        const payload = {schemaVersion: draftModule.SCHEMA,
            expectedParentReceiptSha256: parent.expectedParentReceiptSha256, rows, partial: false};
        const rebuilt = draftModule.rebuild(payload, parent, SPEEDS, clipFrames, transitionProblem);
        return rebuilt[0].sourcePath === 'parent-private-path'
            && rebuilt[0].candidateId === 'already-saved-replacement'
            && !('extra' in rebuilt[0].speed) && parent.audioMix.bgm.trackId === 'saved-music';
    }""")


def test_new_replacement_freezes_even_with_same_clip_coordinates(studio_plan):
    mount(studio_plan)
    backup(studio_plan)
    studio_plan.page.evaluate("""() => {
        const c = ce.clips[0];
        ce.ops.replace(c.clipId, {...c, candidateId: 'new-source-same-times'});
    }""")
    studio_plan.page.wait_for_function("() => ce.drafts.payload?.partial")
    studio_plan.page.reload()
    mount(studio_plan)
    assert studio_plan.page.evaluate("ce.drafts.message") == "上次镜头快照；之后的修改未备份"


def test_without_work_identity_never_writes(studio_plan):
    mount(studio_plan, None)
    studio_plan.page.evaluate("ce.ops.speed(ce.clips[0].clipId, 1, 2)")
    assert studio_plan.page.evaluate("ce.drafts.key") is None
    assert "不会备份" in studio_plan.page.evaluate("ce.drafts.message")


def test_storage_failure_preserves_input_and_original(studio_plan):
    mount(studio_plan)
    backup(studio_plan)
    page = studio_plan.page
    before = page.evaluate("localStorage.getItem(ce.drafts.key)")
    page.evaluate("""() => {
        window.originalDraftSet = Storage.prototype.setItem;
        Storage.prototype.setItem = function(key, value) {
            if (key.startsWith('studio-clip-draft-v1:')) throw Error('quota');
            return window.originalDraftSet.call(this, key, value);
        };
        ce.ops.speed(ce.clips[0].clipId, 2, 1);
    }""")
    page.wait_for_function("() => ce.drafts.message.includes('保留输入与原存储')")
    assert page.evaluate("ce.clips[0].speed.numerator") == 2
    assert page.evaluate("localStorage.getItem(ce.drafts.key)") == before
    page.evaluate("() => { Storage.prototype.setItem = window.originalDraftSet; }")


def test_restore_is_one_undo_and_explicit_discard_only_current_key(studio_plan):
    mount(studio_plan)
    backup(studio_plan)
    page = studio_plan.page
    page.evaluate("ce.ops.mix({sourceGainDb: -9})")
    page.wait_for_function("() => ce.drafts.payload?.partial")
    page.evaluate("ce.restoreDraft(() => true)")
    page.wait_for_function("() => ce.audio.mix.sourceGainDb !== -9")
    page.evaluate("ce.ops.undo()")
    page.wait_for_function("() => ce.audio.mix.sourceGainDb === -9")
    page.evaluate("localStorage.setItem('unrelated-draft', 'keep'); ce.drafts.discard()")
    assert page.evaluate("localStorage.getItem(ce.drafts.key)") is None
    assert page.evaluate("localStorage.getItem('unrelated-draft')") == "keep"


def test_real_work_ui_refresh_restore_then_explicit_save(studio_plan):
    studio = studio_plan
    page, expect = studio.page, studio.expect
    page.route(
        "**/api/runs?*",
        lambda route: route.fulfill(
            json={"runs": [{"id": "run", "sourceName": "测试录像", "completedEligible": True}]}
        ),
    )
    page.reload()
    work = new_work(studio)
    page.get_by_label("游戏", exact=True).fill("草稿恢复")
    page.get_by_label("测试录像", exact=True).check()
    page.get_by_label("生成后让AI再策划").uncheck()
    page.get_by_role("button", name="生成方案", exact=True).click()
    expect(page.locator(".timeline .clip")).to_have_count(3)
    page.get_by_role("tab", name="镜头", exact=True).click()
    expect(page.get_by_label("版本保存状态")).to_be_visible()
    page.wait_for_timeout(150)
    page.locator(".timeline .clip").first.click()
    assert page.get_by_label("镜头编辑", exact=True).count(), page.locator("aside").inner_text()
    page.get_by_label("速度", exact=False).select_option("1/2")
    expect(page.get_by_label("镜头快照状态")).to_contain_text("最近镜头快照")
    import json

    remembered = page.evaluate("localStorage.getItem('studio-last-job-v1')")
    page.add_init_script(f"localStorage.setItem('studio-last-job-v1', {json.dumps(remembered)});")
    page.reload()
    expect(page.get_by_label("当前作品")).to_have_value(work)
    expect(page.get_by_role("button", name="恢复镜头快照", exact=True)).to_be_visible()
    page.get_by_role("button", name="恢复镜头快照", exact=True).click()
    page.locator(".timeline .clip").first.click()
    expect(page.get_by_label("速度", exact=False)).to_have_value("1/2")
    expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_enabled()
    # A local synthesis task must hold the restore/discard gates until completion.
    page.get_by_role("tab", name="声音", exact=True).click()
    page.get_by_role("button", name="手写旁白稿", exact=True).click()
    page.get_by_role("textbox", name="旁白稿", exact=True).fill("测试镜头恢复")
    narration = []
    page.route("**/api/creation/narrations", lambda route: narration.append(route))
    page.get_by_role("button", name="合成旁白", exact=True).click()
    expect(page.get_by_role("button", name="恢复镜头快照", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="丢弃镜头快照", exact=True)).to_be_disabled()
    assert narration
    narration[0].fulfill(status=400, json={"error": {"message": "local fixture task finished"}})
    expect(page.get_by_role("button", name="恢复镜头快照", exact=True)).to_be_enabled()
    with page.expect_response(
        lambda response: (
            response.url.endswith("/api/creation/revisions") and response.request.method == "POST"
        )
    ) as response:
        page.get_by_role("button", name="保存版本", exact=True).click()
    saved = response.value.json()
    from concurrent.futures import ThreadPoolExecutor

    from test_creation_jobs import finish

    with ThreadPoolExecutor(max_workers=1) as worker:
        job = worker.submit(finish, studio.service, saved["jobId"]).result()
    assert job["status"] == "completed", job.get("error")
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()


def test_undo_to_clean_removes_backup_but_initial_clean_keeps_it(studio_plan):
    mount(studio_plan)
    backup(studio_plan)
    studio_plan.page.evaluate("ce.ops.undo()")
    studio_plan.page.wait_for_function(
        "() => !ce.dirty && localStorage.getItem(ce.drafts.key) === null"
    )


@pytest.mark.parametrize("operation", ["trim", "move", "remove", "speed", "transition"])
def test_each_supported_clip_edit_survives_reload(studio_plan, operation):
    mount(studio_plan)
    page = studio_plan.page
    original = page.evaluate("draftModule.clipRows(ce.clips)")
    page.evaluate(
        """operation => {
        const c = ce.clips[0];
        if (operation === 'trim') ce.ops.trim(c.clipId, 'endUs', (c.endUs - 100000) / 1e6);
        if (operation === 'move') ce.ops.move(c.clipId, 1);
        if (operation === 'remove') ce.ops.remove(c.clipId);
        if (operation === 'speed') ce.ops.speed(c.clipId, 1, 2);
        if (operation === 'transition') ce.ops.transition(ce.clips[1].clipId, 1);
    }""",
        operation,
    )
    page.wait_for_function("() => ce.drafts.payload !== null")
    expected = page.evaluate("draftModule.clipRows(ce.clips)")
    assert expected != original
    page.reload()
    mount(studio_plan)
    page.evaluate("ce.restoreDraft(() => true)")
    page.wait_for_function("() => ce.dirty")
    assert page.evaluate("draftModule.clipRows(ce.clips)") == expected


def test_real_saved_parent_audio_binding_survives_recovery(studio_audio):
    from types import SimpleNamespace

    page = studio_audio
    last = page.evaluate(
        "JSON.parse(localStorage.getItem('studio-last-job-v1'))['artifacts/project']"
    )
    fixture = SimpleNamespace(page=page, root=last["id"], plan_id="hook-first")
    mount(fixture)
    original_audio = page.evaluate("ce.audio")
    assert original_audio["narration"] and original_audio["mix"]["bgm"]
    backup(fixture)
    page.evaluate("ce.ops.mix({sourceGainDb: -3})")
    page.wait_for_function("() => ce.drafts.payload?.partial")
    page.evaluate("ce.restoreDraft(() => true)")
    page.wait_for_function("() => ce.audio.mix.sourceGainDb !== -3")
    assert page.evaluate("ce.audio") == original_audio


def test_restore_pending_get_cannot_land_after_local_synthesis_starts(studio_plan):
    studio = studio_plan
    page, expect = studio.page, studio.expect
    page.route(
        "**/api/runs?*",
        lambda route: route.fulfill(
            json={"runs": [{"id": "run", "sourceName": "测试录像", "completedEligible": True}]}
        ),
    )
    page.reload()
    work = new_work(studio)
    page.get_by_label("游戏", exact=True).fill("草稿恢复")
    page.get_by_label("测试录像", exact=True).check()
    page.get_by_label("生成后让AI再策划").uncheck()
    page.get_by_role("button", name="生成方案", exact=True).click()
    expect(page.locator(".timeline .clip")).to_have_count(3)
    page.get_by_role("tab", name="镜头", exact=True).click()
    expect(page.get_by_label("版本保存状态")).to_be_visible()
    page.wait_for_timeout(150)
    page.locator(".timeline .clip").first.click()
    assert page.get_by_label("镜头编辑", exact=True).count(), page.locator("aside").inner_text()
    page.get_by_label("速度", exact=False).select_option("1/2")
    expect(page.get_by_label("镜头快照状态")).to_contain_text("最近镜头快照")
    import json

    remembered = page.evaluate("localStorage.getItem('studio-last-job-v1')")
    page.add_init_script(f"localStorage.setItem('studio-last-job-v1', {json.dumps(remembered)});")
    page.reload()
    expect(page.get_by_label("当前作品")).to_have_value(work)
    expect(page.get_by_role("button", name="恢复镜头快照", exact=True)).to_be_visible()
    parent_reads = []
    page.route(
        "**/api/creation/jobs/*/edit?*", lambda route: parent_reads.append((route, route.fetch()))
    )
    stored = page.evaluate(
        "Object.entries(localStorage).filter(([k]) => k.startsWith('studio-clip-draft-v1:'))"
    )
    with page.expect_request("**/api/creation/jobs/*/edit?*"):
        page.get_by_role("button", name="恢复镜头快照", exact=True).click()
    page.wait_for_timeout(100)
    assert parent_reads
    page.get_by_role("tab", name="声音", exact=True).click()
    page.get_by_role("button", name="手写旁白稿", exact=True).click()
    page.get_by_role("textbox", name="旁白稿", exact=True).fill("延迟恢复期间的本机合成")
    narration = []
    page.route("**/api/creation/narrations", lambda route: narration.append(route))
    page.get_by_role("button", name="合成旁白", exact=True).click()
    expect(page.get_by_role("button", name="恢复镜头快照", exact=True)).to_be_disabled()
    parent_reads[0][0].fulfill(response=parent_reads[0][1])
    page.wait_for_timeout(350)
    expect(page.get_by_text("方案原样", exact=True)).to_be_visible()
    assert (
        page.evaluate(
            "Object.entries(localStorage).filter(([k]) => k.startsWith('studio-clip-draft-v1:'))"
        )
        == stored
    )
    assert narration
    narration[0].fulfill(status=400, json={"error": {"message": "local fixture task finished"}})
    expect(page.get_by_role("button", name="恢复镜头快照", exact=True)).to_be_enabled()
    page.unroute("**/api/creation/jobs/*/edit?*")
    page.get_by_role("button", name="恢复镜头快照", exact=True).click()
    page.locator(".timeline .clip").first.click()
    expect(page.get_by_label("速度", exact=False)).to_have_value("1/2")
