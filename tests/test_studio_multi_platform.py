"""Real media and HTTP projection coverage for Studio multi-platform packages."""

import asyncio
import copy
import json
import subprocess
import threading
import zipfile
from urllib.request import urlopen
from uuid import uuid4

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_publication import ROOT, payload, rendered  # noqa: F401

from gamingcreator.ui import package_jobs
from gamingcreator.ui.server import create_server


def test_real_studio_two_packages_and_projection(rendered, monkeypatch):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    jobs, render = rendered
    profiles = copy.deepcopy(package_jobs.profiles()["profiles"][:2])
    for profile in profiles:
        for kind in ("video", "cover"):
            for key in ("width", "height"):
                value = profile["Fields"][kind][key] // 10
                profile["Fields"][kind][key] = value + value % 2
    monkeypatch.setattr(package_jobs, "profiles", lambda: {"profiles": profiles})
    original = package_jobs.encode

    started, release = threading.Event(), threading.Event()
    encodes = []

    async def encode(repository, *args):
        encodes.append(True)
        if len(encodes) == 2:
            raise ValueError("intentional fixture encode failure")
        started.set()
        await asyncio.to_thread(release.wait, 30)
        return await original(ROOT, *args)

    monkeypatch.setattr(package_jobs, "encode", encode)
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base + "/studio")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.evaluate(
                """async (renderId) => {
                const {h, render} = await import('/assets/vendor/preact.module.js');
                const {PublishWorkspace} = await import('/assets/studio/publish.js');
                render(h(PublishWorkspace, {project:'artifacts/project', works:[{jobId:renderId,kind:'render',status:'completed',createdAt:'2026-11-07'}], open:{id:renderId,kind:'render'}, onWorksChanged:()=>{}, layout:{bin:true,insp:true}}), document.body);
            }""",
                render,
            )
            page.get_by_role("button", name="保存发布信息").click()
            playwright.expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible(
                timeout=30000
            )
            lost = []

            def lose_response(route):
                response = route.fetch()
                lost.append(response.json()["jobId"])
                route.abort()

            page.route("**/api/creation/packages", lose_response, times=1)
            page.get_by_role("checkbox").nth(1).check()
            page.get_by_role("button", name="生成平台包", exact=True).click()
            for _ in range(150):
                if started.is_set():
                    break
                page.wait_for_timeout(100)
            assert started.is_set()
            page.wait_for_function(
                "document.querySelector('[role=status]')?.textContent.includes('fetch') || !document.querySelector('button.btn:disabled')",
                timeout=15000,
            )
            first = [s for s in jobs._statuses() if s["kind"] == "package"]
            assert len(first) == 1
            pub = first[0]["parentJobId"]
            page.reload()
            page.evaluate(
                """async (pubId) => {
                const {h, render} = await import('/assets/vendor/preact.module.js');
                const {PublishWorkspace} = await import('/assets/studio/publish.js');
                render(h(PublishWorkspace, {project:'artifacts/project', works:[], open:{id:pubId,kind:'publication'}, onWorksChanged:()=>{}, layout:{bin:true,insp:true}}), document.body);
            }""",
                pub,
            )
            playwright.expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
            assert [s["jobId"] for s in jobs._statuses() if s["kind"] == "package"] == [
                first[0]["jobId"]
            ]
            assert lost == [first[0]["jobId"]]
            page.get_by_role("checkbox").nth(1).check()
            page.get_by_role("button", name="生成平台包", exact=True).click()
            page.wait_for_timeout(200)
            assert len([s for s in jobs._statuses() if s["kind"] == "package"]) == 1
            release.set()
            links = page.get_by_role("link", name="下载平台包（zip）", exact=True)
            retry = page.get_by_role("button", name="重试此平台")
            playwright.expect(retry).to_be_visible(timeout=30000)
            playwright.expect(links).to_have_count(1)
            page.route("**/api/creation/packages", lose_response, times=1)
            retry.click()
            playwright.expect(links).to_have_count(2, timeout=60000)
            retry.click()
            page.wait_for_timeout(200)
            attempts = [s for s in jobs._statuses() if s["kind"] == "package"]
            assert len(attempts) == 3
            assert len([s for s in attempts if s["status"] == "failed"]) == 1
            pubs = [s for s in jobs._statuses() if s["kind"] == "publication"]
            assert len(pubs) == 1
            pub = pubs[0]["jobId"]
            for link in links.all():
                with page.expect_download() as downloaded:
                    link.click()
                with zipfile.ZipFile(downloaded.value.path()) as archive:
                    assert set(archive.namelist()) == set(package_jobs.FILES)
                    assert archive.read("title.txt").decode() == jobs.publication(pub)["title"]
                    target = jobs.repository / (uuid4().hex + ".mp4")
                    target.write_bytes(archive.read("video.mp4"))
                    subprocess.run(
                        [
                            str(ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"),
                            "-v",
                            "error",
                            "-i",
                            str(target),
                            "-f",
                            "null",
                            "-",
                        ],
                        check=True,
                        capture_output=True,
                    )
            # Catalog truncation must not hide the original package attempts.
            for _ in range(105):
                directory = jobs.jobs / uuid4().hex
                directory.mkdir()
                jobs.save(
                    directory / "status.json",
                    {
                        "jobId": directory.name,
                        "kind": "plan",
                        "status": "failed",
                        "projectId": "artifacts/project",
                        "createdAt": "2099-01-01",
                    },
                )
            import gamingcreator.ui.creation_jobs as implementation

            original_hash = implementation.hash_file

            def no_video_hash(path):
                assert path.suffix != ".mp4"
                return original_hash(path)

            monkeypatch.setattr(implementation, "hash_file", no_video_hash)
            with urlopen(
                base + f"/api/creation/jobs/{pub}/packages?projectId=artifacts/project"
            ) as response:
                rows = json.load(response)["jobs"]
            assert len(rows) == 3
            assert {r["platform"] for r in rows} == {p["Platform"] for p in profiles}
            assert all(r["parentJobId"] == pub for r in rows)
            assert not errors
            browser.close()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join()


def test_free_same_render_new_publication_cannot_add_platform(rendered, monkeypatch):  # noqa: F811
    from gamingcreator.domain.errors import AppError

    jobs, render = rendered
    jobs.select_plan("free")
    original = package_jobs.encode

    async def encode(repository, *args):
        return await original(ROOT, *args)

    monkeypatch.setattr(package_jobs, "encode", encode)
    pubs = []
    for _ in range(2):
        pub = jobs.submit("publication", payload(jobs, render))["jobId"]
        assert finish(jobs, pub)["status"] == "completed"
        pubs.append(pub)
    profiles = package_jobs.profiles()["profiles"]
    profile = profiles[0]
    for kind in ("video", "cover"):
        for key in ("width", "height"):
            value = profile["Fields"][kind][key] // 10
            profile["Fields"][kind][key] = value + value % 2
    request = {
        "requestId": uuid4().hex,
        "publicationJobId": pubs[0],
        "expectedPublicationReceiptSha256": jobs.publication(pubs[0])["publicationReceiptSha256"],
        "profile": profile,
    }
    accepted = jobs.submit("package", request)["jobId"]
    assert finish(jobs, accepted)["status"] == "completed"
    assert jobs.submit("package", request)["jobId"] == accepted
    for pub in pubs:
        with pytest.raises(AppError) as error:
            jobs.submit(
                "package",
                {
                    "requestId": uuid4().hex,
                    "publicationJobId": pub,
                    "expectedPublicationReceiptSha256": jobs.publication(pub)[
                        "publicationReceiptSha256"
                    ],
                    "profile": profiles[1],
                },
            )
        assert error.value.code == "entitlement.denied"
    assert len([s for s in jobs._statuses() if s["kind"] == "package"]) == 1
    stored = jobs.read(jobs.directory(accepted) / "request.json")
    stored["request"]["publicationJobId"] = pubs[1]
    jobs.save(jobs.directory(accepted) / "request.json", stored)
    with pytest.raises(ValueError, match="identity"):
        jobs.packages(pubs[0], "artifacts/project")


@pytest.mark.parametrize("changed_project", [False, True])
@pytest.mark.parametrize("late_error", [False, True])
def test_late_publication_response_cannot_replace_new_project(service, changed_project, late_error):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    old, new = "a" * 32, "b" * 32
    pending = []
    snapshot = {
        "publicationJobId": new,
        "publicationReceiptSha256": "d" * 64,
        "renderJobId": "c" * 32,
        "title": "新项目版本",
        "description": "",
        "tags": [],
        "coverFrame": 0,
        "frames": 4,
        "width": 64,
        "height": 48,
        "fps": {"numerator": 2, "denominator": 1},
    }
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base + "/studio")

            def answer(route):
                path = route.request.url.split("?", 1)[0]
                if path.endswith(f"/{old}/publication"):
                    pending.append(route)
                elif path.endswith(f"/{new}/publication"):
                    route.fulfill(json=snapshot)
                elif path.endswith("/packages"):
                    route.fulfill(json={"jobs": []})
                elif path.endswith("/platform-profiles"):
                    route.fulfill(json={"profiles": []})
                else:
                    route.continue_()

            page.route("**/api/creation/**", answer)
            mount = """async ({id,project}) => {
                const {h, render} = await import('/assets/vendor/preact.module.js');
                const {PublishWorkspace} = await import('/assets/studio/publish.js');
                render(h(PublishWorkspace, {project, works:[], open:{id,kind:'publication'}, onWorksChanged:()=>{}, layout:{bin:true,insp:true}}), document.body);
            }"""
            page.evaluate(mount, {"id": old, "project": "old-project"})
            for _ in range(50):
                if pending:
                    break
                page.wait_for_timeout(20)
            assert pending
            page.evaluate(
                mount, {"id": new, "project": "new-project" if changed_project else "old-project"}
            )
            title = page.locator("[aria-label=发布信息] input").first
            playwright.expect(title).to_have_value("新项目版本")
            if late_error:
                pending[0].fulfill(status=400, json={"error": "旧请求错误"})
            else:
                pending[0].fulfill(json={**snapshot, "publicationJobId": old, "title": "旧响应"})
            page.wait_for_timeout(100)
            playwright.expect(title).to_have_value("新项目版本")
            assert page.get_by_text("旧请求错误", exact=True).count() == 0
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("late_error", [False, True])
@pytest.mark.parametrize("changed_project", [False, True])
def test_switch_stops_late_batch_submit_and_catch_finally(service, late_error, changed_project):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    old, new = "a" * 32, "b" * 32
    pending, posts = [], []
    snapshot = {
        "publicationReceiptSha256": "d" * 64,
        "renderJobId": "c" * 32,
        "title": "旧版本",
        "description": "",
        "tags": [],
        "coverFrame": 0,
        "frames": 4,
        "width": 64,
        "height": 48,
        "fps": {"numerator": 2, "denominator": 1},
    }
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base + "/studio")

            def answer(route):
                path = route.request.url.split("?", 1)[0]
                if path.endswith("/publication"):
                    pub = path.split("/")[-2]
                    route.fulfill(
                        json={
                            **snapshot,
                            "publicationJobId": pub,
                            "publicationReceiptSha256": ("e" if pub == new else "d") * 64,
                            "title": "新版本" if pub == new else "旧版本",
                        }
                    )
                elif path.endswith("/packages") and route.request.method == "GET":
                    route.fulfill(json={"jobs": []})
                elif path.endswith("/packages"):
                    posts.append(route.request.post_data_json)
                    pending.append(route)
                elif path.endswith("/platform-profiles"):
                    route.fulfill(
                        json={
                            "profiles": [
                                {"Platform": p, "Fields": {"limits": {}}}
                                for p in ("bilibili", "douyin")
                            ]
                        }
                    )
                else:
                    route.fulfill(json={"jobs": []})

            page.route("**/api/creation/**", answer)
            mount = """async ({id,project}) => {
                const {h, render} = await import('/assets/vendor/preact.module.js');
                const {PublishWorkspace} = await import('/assets/studio/publish.js');
                render(h(PublishWorkspace, {project, works:[], open:{id,kind:'publication'}, onWorksChanged:()=>{}, layout:{bin:true,insp:true}}), document.body);
            }"""
            page.evaluate(mount, {"id": old, "project": "old"})
            playwright.expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
            page.get_by_role("checkbox").nth(1).check()
            page.get_by_role("button", name="生成平台包", exact=True).click()
            for _ in range(100):
                if pending:
                    break
                page.wait_for_timeout(20)
            assert len(posts) == 1
            page.evaluate(mount, {"id": new, "project": "new" if changed_project else "old"})
            title = page.locator("[aria-label=发布信息] input").first
            playwright.expect(title).to_have_value("新版本")
            # Start the new version too: the old finally must not clear its busy state.
            page.get_by_role("button", name="生成平台包", exact=True).click()
            for _ in range(100):
                if len(pending) == 2:
                    break
                page.wait_for_timeout(20)
            assert len(posts) == 2
            if late_error:
                pending[0].fulfill(status=400, json={"error": "旧批次错误"})
            else:
                pending[0].fulfill(json={"jobId": "f" * 32, "status": "pending"})
            page.wait_for_timeout(150)
            playwright.expect(title).to_have_value("新版本")
            playwright.expect(
                page.get_by_role("button", name="正在生成…", exact=True)
            ).to_be_disabled()
            assert page.get_by_text("旧批次错误", exact=True).count() == 0
            assert len(posts) == 2
            assert posts[0]["publicationJobId"] == old
            assert posts[1]["publicationJobId"] == new
            assert posts[1]["expectedPublicationReceiptSha256"] == "e" * 64
            pending[1].abort()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_main_project_switch_does_not_reopen_old_publication(service):  # noqa: F811
    from urllib.parse import parse_qs, urlsplit

    playwright = pytest.importorskip("playwright.sync_api")
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    old, new = "a" * 32, "b" * 32
    pending, opened, posted = [], [], []
    snapshot = {
        "publicationReceiptSha256": "d" * 64,
        "renderJobId": "c" * 32,
        "description": "",
        "tags": [],
        "coverFrame": 0,
        "frames": 4,
        "width": 64,
        "height": 48,
        "fps": {"numerator": 2, "denominator": 1},
    }
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()

            def answer(route):
                url = urlsplit(route.request.url)
                if url.path == "/api/projects":
                    route.fulfill(
                        json={"projects": [{"path": p, "name": p} for p in ("old", "new")]}
                    )
                elif url.path == "/api/creation/jobs":
                    if parse_qs(url.query).get("projectId") == ["new"]:
                        pending.append(route)
                    else:
                        route.fulfill(
                            json={
                                "jobs": [
                                    {
                                        "jobId": old,
                                        "kind": "publication",
                                        "status": "completed",
                                        "createdAt": "2026-11-07",
                                    }
                                ]
                            }
                        )
                elif url.path.endswith("/publication"):
                    pub = url.path.split("/")[-2]
                    opened.append(pub)
                    route.fulfill(
                        json={
                            **snapshot,
                            "publicationJobId": pub if pub == old else None,
                            "title": "旧项目文案" if pub == old else "新项目草稿",
                        }
                    )
                elif url.path.endswith("/packages"):
                    if route.request.method == "POST":
                        posted.append(route.request.post_data_json)
                    route.fulfill(json={"jobs": []})
                elif url.path.endswith("/platform-profiles"):
                    route.fulfill(
                        json={"profiles": [{"Platform": "bilibili", "Fields": {"limits": {}}}]}
                    )
                else:
                    route.fulfill(json={"runs": []})

            page.route("**/api/**", answer)
            page.goto(base + "/studio")
            page.get_by_text("封面与文案（1）", exact=True).click()
            page.get_by_title("在发布区打开", exact=True).click()
            title = page.locator("[aria-label=发布信息] input").first
            playwright.expect(title).to_have_value("旧项目文案")
            page.get_by_role("combobox", name="项目", exact=True).select_option("new")
            for _ in range(50):
                if pending:
                    break
                page.wait_for_timeout(20)
            assert pending
            assert page.get_by_text("旧项目文案", exact=True).count() == 0
            playwright.expect(
                page.get_by_role("button", name="生成平台包", exact=True)
            ).to_be_disabled()
            pending[0].fulfill(
                json={
                    "jobs": [
                        {
                            "jobId": new,
                            "kind": "render",
                            "status": "completed",
                            "createdAt": "2026-11-07",
                        }
                    ]
                }
            )
            playwright.expect(title).to_have_value("新项目草稿")
            assert opened == [old, new]
            assert not posted
            assert page.get_by_role("link", name="下载平台包（zip）", exact=True).count() == 0
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_retry_unknown_before_registration_survives_refresh(rendered, monkeypatch):  # noqa: F811
    """Actual HTTP POSTs wait before registration while GET still exposes only old failure."""
    from gamingcreator.ui.creation_jobs import CreationJobs

    playwright = pytest.importorskip("playwright.sync_api")
    jobs, render = rendered
    pub = jobs.submit("publication", payload(jobs, render))["jobId"]
    assert finish(jobs, pub)["status"] == "completed"
    profile = package_jobs.profiles()["profiles"][0]
    for kind in ("video", "cover"):
        for key in ("width", "height"):
            value = profile["Fields"][kind][key] // 10
            profile["Fields"][kind][key] = value + value % 2
    monkeypatch.setattr(package_jobs, "profiles", lambda: {"profiles": [profile]})
    original_encode = package_jobs.encode

    async def fail_encode(*args):
        raise ValueError("initial terminal failure")

    monkeypatch.setattr(package_jobs, "encode", fail_encode)
    failed = jobs.submit(
        "package",
        {
            "requestId": uuid4().hex,
            "publicationJobId": pub,
            "expectedPublicationReceiptSha256": jobs.publication(pub)["publicationReceiptSha256"],
            "profile": profile,
        },
    )["jobId"]
    assert finish(jobs, failed)["status"] == "failed"

    async def encode(repository, *args):
        return await original_encode(ROOT, *args)

    monkeypatch.setattr(package_jobs, "encode", encode)
    release = threading.Event()
    received = []
    original_submit = CreationJobs.submit

    def gated_submit(self, kind, request):
        if kind == "package":
            received.append(request["requestId"])
            assert release.wait(30)
        return original_submit(self, kind, request)

    monkeypatch.setattr(CreationJobs, "submit", gated_submit)
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.add_init_script("""{
                const original = window.fetch.bind(window);
                window.fetch = (url, options) => {
                    if (String(url).includes('/api/creation/packages') && options?.method === 'POST') {
                        const count = Number(sessionStorage.getItem('fixture-lost') || 0);
                        sessionStorage.setItem('fixture-lost', String(count + 1));
                        const request = original(url, options);
                        if (count < 2) { request.catch(() => {}); return Promise.reject(new TypeError('fixture connection lost before registration')); }
                        return request;
                    }
                    return original(url, options);
                };
            }""")
            mount = """async (id) => {
                const {h, render} = await import('/assets/vendor/preact.module.js');
                const {PublishWorkspace} = await import('/assets/studio/publish.js');
                render(h(PublishWorkspace, {project:'artifacts/project', works:[], open:{id,kind:'publication'}, onWorksChanged:()=>{}, layout:{bin:true,insp:true}}), document.body);
            }"""
            page.goto(base + "/studio")
            page.evaluate(mount, pub)
            retry = page.get_by_role("button", name="重试此平台", exact=True)
            for count in (1, 2):
                playwright.expect(retry).to_be_enabled()
                retry.click()
                for _ in range(100):
                    if len(received) >= count:
                        break
                    page.wait_for_timeout(20)
                assert len(received) == count
                playwright.expect(
                    page.get_by_role("button", name="生成平台包", exact=True)
                ).to_be_enabled()
                assert [
                    row["jobId"] for row in jobs.packages(pub, "artifacts/project")["jobs"]
                ] == [failed]
            page.reload()
            page.evaluate(mount, pub)
            playwright.expect(retry).to_be_enabled()
            retry.click()
            for _ in range(100):
                if len(received) == 3:
                    break
                page.wait_for_timeout(20)
            assert len(received) == 3 and len(set(received)) == 1
            release.set()
            playwright.expect(
                page.get_by_role("link", name="下载平台包（zip）", exact=True)
            ).to_be_visible(timeout=30000)
            rows = jobs.packages(pub, "artifacts/project")["jobs"]
            assert len(rows) == 2 and {r["status"] for r in rows} == {"failed", "completed"}
            stored = jobs.read(
                jobs.directory(next(r["jobId"] for r in rows if r["status"] == "completed"))
                / "request.json"
            )
            assert stored["request"]["requestId"] == received[0]
            blocked = page.evaluate("""async () => {
                const client = await import('/assets/studio/api.js');
                const original = Storage.prototype.setItem;
                Storage.prototype.setItem = () => { throw new Error('fixture storage denied'); };
                try { await client.submit('package', {profile:{Platform:'douyin'}}, 'fixture-storage-blocked'); }
                catch (error) { return {code:error.code, message:error.message}; }
                finally { Storage.prototype.setItem = original; }
            }""")
            assert blocked["code"] == "intent.storage"
            assert "会话存储" in blocked["message"]
            assert len(received) == 3
            browser.close()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join()
