"""Local narration jobs: offline fake engine, version attachment, restart and fail-closed paths."""

# ruff: noqa: F811
import hashlib
import json
import math
import threading
import wave
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401

from gamingcreator.application.narration import LocalVoice
from gamingcreator.domain.creation_audio import AudioMix
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import sapi_narration as sapi
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.ui import narration_jobs
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.revision_jobs import load_chain
from gamingcreator.ui.server import create_server

VOICE = LocalVoice("v1", "Fixture 中文", "804")
SECONDS_PER_CHAR = 0.1


class Engine:
    """Stands in for COM: duration is 0.1 s per text character, so tests choose any length."""

    def __init__(self):
        self.voices = [VOICE]
        self.synthesized = 0
        self.block = False
        self.started = threading.Event()

    async def invoke(self, mode, request_path, context):
        context.check_cancelled()
        if mode == "list":
            return json.dumps(
                [
                    {"voiceId": v.voice_id, "description": v.description, "language": v.language}
                    for v in self.voices
                ]
            ).encode()
        self.synthesized += 1
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if self.block:
            self.started.set()
            await context.cancelled.wait()
            context.check_cancelled()
        count = round(len(request["text"]) * SECONDS_PER_CHAR * 22050)
        with wave.open(request["wavPath"], "wb") as wav:
            wav.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
            wav.writeframes(
                b"".join(
                    round(16000 * math.sin(2 * math.pi * 660 * i / 22050)).to_bytes(
                        2, "little", signed=True
                    )
                    for i in range(count)
                )
            )
        return b"{}"


@pytest.fixture
def engine(monkeypatch, tmp_path):
    fake = Engine()
    monkeypatch.setattr(sapi, "_invoke", fake.invoke)
    # The voice scratch directory is derived from the helper location; keep it in tmp.
    monkeypatch.setattr(sapi, "_HELPER", tmp_path / "voice-host/scripts/sapi-narration.ps1")
    return fake


@pytest.fixture
def narrated(revisions, engine, monkeypatch):
    jobs, root, calls = revisions
    seen = []

    async def render(
        self,
        plan,
        output,
        protected,
        context,
        width,
        height,
        digest,
        cues,
        mode,
        *,
        audio_mix=None,
        music=None,
        narration=None,
        narration_artifact=None,
    ):
        from gamingcreator.infrastructure.narration_mix import narration_receipt, verify_narration

        calls.append(plan)
        seen.append((narration, narration_artifact))
        output.mkdir()
        (output / "video.mp4").write_bytes(b"narrated-video")
        files = {"video.mp4": hash_file(output / "video.mp4")}
        receipt = {
            "schemaVersion": "creation-render-receipt-v1",
            "status": "completed",
            "files": files,
            "creationReceiptSha256": digest,
            "width": width,
            "height": height,
            "frames": plan.frames,
            "fpsNumerator": plan.fps,
            "subtitles": {"mode": mode, "cueCount": len(cues)},
            "audioMix": (audio_mix or AudioMix()).to_json(),
            "music": None if music is None else music.public(),
        }
        if mode != "none":
            (output / "subtitles.srt").write_bytes(b"")
            files["subtitles.srt"] = hash_file(output / "subtitles.srt")
        if narration is not None:
            checked = verify_narration(narration, narration_artifact)
            (output / "narration.txt").write_bytes(checked.text_path.read_bytes())
            files["narration.txt"] = hash_file(output / "narration.txt")
            receipt["narration"] = narration_receipt(narration, checked, plan.fps)
        (output / "receipt.json").write_text(json.dumps(receipt))

    monkeypatch.setattr(FfmpegCreationRenderer, "render", render)
    return SimpleNamespace(jobs=jobs, root=root, engine=engine, seen=seen)


_counter = iter(range(0x1000, 0xFFFF))


def narrate(jobs, text="旁白", voice="v1", project="artifacts/project"):
    request = {
        "requestId": f"{next(_counter):032x}",
        "projectId": project,
        "text": text,
        "voiceId": voice,
    }
    return jobs.submit("narration", request)["jobId"]


def done(jobs, text="旁白", **kwargs):
    state = finish(jobs, narrate(jobs, text, **kwargs))
    assert state["status"] == "completed", state
    return state


def choice(state, start=3, gain=-6, duck="narration-v1"):
    asset = state["narrationAsset"]
    return {
        "assetJobId": asset["assetJobId"],
        "receiptSha256": asset["receiptSha256"],
        "startFrame": start,
        "gainDb": gain,
        "ducking": duck,
    }


def total_frames(jobs, job_id):
    return load_chain(jobs, job_id).plan.frames


def revise(jobs, parent, token, **fields):
    request = payload(jobs, parent, token)
    request.update(fields)
    return finish(jobs, jobs.submit("revision", request)["jobId"])


def test_generate_persist_restart_without_resynthesis(narrated):
    jobs, engine = narrated.jobs, narrated.engine
    state = done(jobs)
    asset = state["narrationAsset"]
    assert asset["assetJobId"] == state["jobId"] and asset["text"] == "旁白"
    assert asset["durationSeconds"] == pytest.approx(0.2, abs=1e-4)
    assert asset["licenseStatus"] == "unknown" and asset["voice"]["voiceId"] == "v1"
    assert asset["audioUrl"] == f"/api/creation/jobs/{state['jobId']}/narration-files/narration.wav"
    assert asset["textUrl"].endswith("narration.txt") and asset["sampleRate"] == 22050
    result = jobs.directory(state["jobId"]) / "result"
    assert {p.name for p in result.iterdir()} == {"narration.wav", "narration.txt", "receipt.json"}
    assert engine.synthesized == 1
    restarted = CreationJobs(jobs.repository)
    assert restarted.get(state["jobId"])["narrationAsset"] == asset
    assert not restarted.threads
    request = jobs.read(jobs.directory(state["jobId"]) / "request.json")["request"]
    assert restarted.submit("narration", request)["jobId"] == state["jobId"]
    assert not restarted.threads and engine.synthesized == 1
    with pytest.raises(AppError) as error:
        restarted.submit("narration", {**request, "text": "另一段"})
    assert error.value.code == "creation.conflict"
    wav = restarted.narration_file(state["jobId"], "narration.wav")
    assert hash_file(wav.path) == wav.sha256 == hash_file(result / "narration.wav")
    assert (
        restarted.narration_file(state["jobId"], "narration.txt").path.read_bytes()
        == "旁白".encode()
    )
    for name in ("receipt.json", "../receipt.json", ""):
        with pytest.raises(ValueError):
            restarted.narration_file(state["jobId"], name)


def test_voice_listing_and_missing_voice_never_completes(narrated):
    jobs, engine = narrated.jobs, narrated.engine
    assert jobs.voices() == {
        "voices": [{"voiceId": "v1", "description": "Fixture 中文", "language": "804"}],
        "licenseStatus": "unknown",
    }
    failed = finish(jobs, narrate(jobs, voice="ghost"))
    assert failed["status"] == "failed" and "narrationAsset" not in failed
    assert engine.synthesized == 0 and not (jobs.directory(failed["jobId"]) / "result").exists()
    assert CreationJobs(jobs.repository).get(failed["jobId"])["status"] == "failed"
    with pytest.raises(ValueError):
        jobs.narration_file(failed["jobId"], "narration.wav")
    # An already generated WAV does not need the voice any more.
    state = done(jobs)
    engine.voices = []
    assert jobs.voices()["voices"] == []
    assert jobs.get(state["jobId"])["status"] == "completed"
    assert (
        finish(
            jobs,
            jobs.submit("revision", {**payload(jobs, narrated.root), "narration": choice(state)})[
                "jobId"
            ],
        )["status"]
        == "completed"
    )


@pytest.mark.parametrize(
    "fault",
    [
        {"text": ""},
        {"text": "\x00"},
        {"text": "x" * 10001},
        {"voiceId": ""},
        {"extra": "field"},
        {"projectId": "../outside"},
    ],
)
def test_invalid_narration_request_is_not_registered(narrated, fault):
    jobs = narrated.jobs
    request = {
        "requestId": "e" * 32,
        "projectId": "artifacts/project",
        "text": "旁白",
        "voiceId": "v1",
        **fault,
    }
    with pytest.raises((ValueError, AppError)):
        jobs.submit("narration", request)
    assert not (jobs.root / ("e" * 32 + ".json")).exists() and narrated.engine.synthesized == 0


def test_cancel_interrupts_and_never_publishes_completed(narrated):
    jobs, engine = narrated.jobs, narrated.engine
    engine.block = True
    job = narrate(jobs, "取消")
    assert engine.started.wait(10)
    assert jobs.cancel_narration(job)["cancelRequested"] is True
    state = finish(jobs, job)
    assert state["status"] == "interrupted" and state["error"]["code"] == "creation.cancelled"
    assert "narrationAsset" not in state
    assert not (jobs.directory(job) / "result").exists()
    restarted = CreationJobs(jobs.repository)
    assert restarted.get(job)["status"] == "interrupted" and not restarted.threads
    assert restarted.cancel_narration(job)["cancelRequested"] is False
    with pytest.raises(ValueError):
        jobs.narration_file(job, "narration.wav")
    with pytest.raises(ValueError):
        jobs.submit(
            "revision",
            {
                **payload(jobs, narrated.root),
                "narration": choice(
                    {"narrationAsset": {"assetJobId": job, "receiptSha256": "0" * 64}}
                ),
            },
        )
    # Completed work and other kinds cannot be cancelled here.
    engine.block = False
    ok = done(jobs)
    assert jobs.cancel_narration(ok["jobId"])["cancelRequested"] is False
    assert jobs.get(ok["jobId"])["status"] == "completed"
    with pytest.raises(ValueError):
        jobs.cancel_narration(narrated.root)
    with pytest.raises(AppError):
        jobs.cancel_narration("f" * 32)
    with pytest.raises(AppError):
        jobs.cancel_narration("../x")


def test_cancel_arriving_after_synthesis_still_interrupts(narrated, monkeypatch):
    jobs = narrated.jobs
    original = narration_jobs.generate
    ready = threading.Event()

    async def generate_then_cancel(self_jobs, directory, request):
        await original(self_jobs, directory, request)
        self_jobs.cancel_narration(directory.name)
        ready.set()

    monkeypatch.setattr(narration_jobs, "generate", generate_then_cancel)
    state = finish(jobs, narrate(jobs, "迟到取消"))
    assert ready.is_set()
    assert state["status"] == "interrupted" and state["error"]["code"] == "creation.cancelled"
    assert "narrationAsset" not in state
    assert not (jobs.directory(state["jobId"]) / "result").exists()
    assert jobs.narration_cancel_requests == set() and jobs.narration_contexts == {}
    with pytest.raises(ValueError):
        jobs.submit(
            "revision",
            {
                **payload(jobs, narrated.root),
                "narration": choice(
                    {
                        "narrationAsset": {
                            "assetJobId": state["jobId"],
                            "receiptSha256": "0" * 64,
                        }
                    }
                ),
            },
        )


def test_attach_inherit_replace_remove_and_ancestors(narrated):
    jobs = narrated.jobs
    speech = done(jobs)
    selection = choice(speech)
    first = revise(jobs, narrated.root, "b", narration=selection)
    assert first["status"] == "completed", first
    assert first["editor"]["narration"] == selection
    assert first["editor"]["narrationAsset"] == speech["narrationAsset"]
    assert "narration" not in jobs.edit(narrated.root, "hook-first")
    inherited = revise(jobs, first["jobId"], "c")
    assert inherited["editor"]["narration"] == selection
    moved = {**selection, "startFrame": 5, "gainDb": -12.5, "ducking": "off"}
    replaced = revise(jobs, inherited["jobId"], "d", narration=moved)
    assert replaced["editor"]["narration"] == moved
    removed = revise(jobs, replaced["jobId"], "e", narration=None)
    assert removed["status"] == "completed" and "narration" not in removed["editor"]
    assert "narrationAsset" not in removed["editor"]
    # Ancestors keep their own selection; a child of the removal stays without narration.
    for job, expected in ((first, selection), (inherited, selection), (replaced, moved)):
        assert jobs.edit(job["jobId"], "hook-first")["narration"] == expected
    assert "narration" not in revise(jobs, removed["jobId"], "f")["editor"]
    # A fresh process re-reads everything from disk with zero workers/synthesis.
    synthesized = narrated.engine.synthesized
    restarted = CreationJobs(jobs.repository)
    assert restarted.edit(inherited["jobId"], "hook-first")["narration"] == selection
    assert restarted.edit(replaced["jobId"], "hook-first")["narration"] == moved
    assert "narration" not in restarted.edit(removed["jobId"], "hook-first")
    assert not restarted.threads and narrated.engine.synthesized == synthesized
    # The recorded request keeps exactly what the user sent (null is not dropped).
    stored = jobs.read(jobs.directory(removed["jobId"]) / "request.json")["request"]
    assert stored["narration"] is None
    metadata = jobs.read(jobs.directory(removed["jobId"]) / "result/revision.json")
    assert metadata["narration"] is None


def test_overlong_or_shortened_narration_is_rejected_and_old_versions_unchanged(narrated):
    jobs = narrated.jobs
    short = done(jobs)  # 0.2 s = 6 frames at 30 fps
    first = revise(jobs, narrated.root, "b", narration=choice(short, start=3))
    frames = total_frames(jobs, first["jobId"])
    long = done(jobs, "长" * (frames // 3 + 2))
    before = {p: p.read_bytes() for p in jobs.directory(first["jobId"]).rglob("*") if p.is_file()}

    def rejected(request):
        with pytest.raises(ValueError, match="旁白长"):
            jobs.submit("revision", request)
        assert not (jobs.root / (request["requestId"] + ".json")).exists()

    rejected({**payload(jobs, first["jobId"], "c"), "narration": choice(long, start=0)})
    rejected({**payload(jobs, first["jobId"], "d"), "narration": choice(short, start=frames - 5)})
    rejected({**payload(jobs, first["jobId"], "9"), "narration": choice(short, start=frames)})
    # Shortening the clips after attachment would silently truncate: refuse it, keep the old one.
    shortened = payload(jobs, first["jobId"], "6")
    for clip in shortened["clips"]:
        clip["outputFrames"] = 1
    rejected(shortened)
    removal = {**payload(jobs, first["jobId"], "7"), "narration": None}
    for clip in removal["clips"]:
        clip["outputFrames"] = 1
    assert finish(jobs, jobs.submit("revision", removal)["jobId"])["status"] == "completed"
    # Exact fit is accepted: the last output sample is the last narration sample.
    exact = revise(jobs, narrated.root, "8", narration=choice(short, start=frames - 6))
    assert exact["status"] == "completed"
    assert before == {
        p: p.read_bytes() for p in jobs.directory(first["jobId"]).rglob("*") if p.is_file()
    }
    assert jobs.get(first["jobId"])["editor"]["narration"]["startFrame"] == 3
    # The long asset itself stays previewable.
    assert jobs.get(long["jobId"])["status"] == "completed"


@pytest.mark.parametrize(
    "fault", ["project", "kind", "digest", "unknown-asset", "extra", "bool-frame", "gain", "duck"]
)
def test_invalid_or_foreign_narration_selection_is_rejected(narrated, tmp_path, fault):
    jobs = narrated.jobs
    (tmp_path / "artifacts/other").mkdir(parents=True)
    (tmp_path / "artifacts/other/timeline.sqlite3").touch()
    own = choice(done(jobs))
    selection = dict(own)
    if fault == "project":
        selection = choice(done(jobs, project="artifacts/other"))
    elif fault == "kind":
        selection["assetJobId"] = narrated.root
    elif fault == "digest":
        selection["receiptSha256"] = "0" * 64
    elif fault == "unknown-asset":
        selection["assetJobId"] = "f" * 32
    elif fault == "extra":
        selection["path"] = "outside"
    elif fault == "bool-frame":
        selection["startFrame"] = True
    elif fault == "gain":
        selection["gainDb"] = 1
    else:
        selection["ducking"] = "source-v1"
    request = {**payload(jobs, narrated.root, "b"), "narration": selection}
    with pytest.raises((ValueError, AppError)):
        jobs.submit("revision", request)
    assert not (jobs.root / ("b" * 32 + ".json")).exists()


@pytest.mark.parametrize("target", ["narration.wav", "narration.txt", "receipt.json"])
def test_tampered_asset_blocks_editor_attachment_and_render(narrated, target):
    jobs = narrated.jobs
    speech = done(jobs)
    revision = revise(jobs, narrated.root, "b", narration=choice(speech))
    render = jobs.submit(
        "render",
        {"requestId": "c" * 32, "revisionJobId": revision["jobId"], "width": 320, "height": 180},
    )["jobId"]
    assert finish(jobs, render)["status"] == "completed"
    later = (
        payload(jobs, revision["jobId"], "d"),
        {**payload(jobs, narrated.root, "e"), "narration": choice(speech)},
    )
    path = jobs.directory(speech["jobId"]) / "result" / target
    path.write_bytes(path.read_bytes() + b" ")
    assert jobs.get(speech["jobId"])["status"] == "failed"
    with pytest.raises(ValueError):
        jobs.narration_file(speech["jobId"], "narration.wav")
    with pytest.raises((ValueError, AppError)):
        jobs.edit(revision["jobId"], "hook-first")
    assert jobs.get(revision["jobId"])["status"] == "failed"
    assert jobs.get(render)["status"] == "failed" and "artifact" not in jobs.get(render)
    for request in later:
        with pytest.raises((ValueError, AppError)):
            jobs.submit("revision", request)
    with pytest.raises((ValueError, AppError)):
        jobs.submit(
            "render",
            {
                "requestId": "f" * 32,
                "revisionJobId": revision["jobId"],
                "width": 320,
                "height": 180,
            },
        )
    assert len(narrated.seen) == 1  # no further renderer call after tampering


def test_render_of_narrated_revision_records_text_and_download_url(narrated):
    jobs = narrated.jobs
    speech = done(jobs, "你好 <&>")
    selection = choice(speech, start=2, gain=-3, duck="off")
    revision = revise(jobs, narrated.root, "b", narration=selection)
    inherited = revise(jobs, revision["jobId"], "c")
    removed = revise(jobs, inherited["jobId"], "d", narration=None)

    def render(parent, token):
        return finish(
            jobs,
            jobs.submit(
                "render",
                {"requestId": token * 32, "revisionJobId": parent, "width": 320, "height": 180},
            )["jobId"],
        )

    with_narration = render(inherited["jobId"], "e")
    assert with_narration["status"] == "completed", with_narration
    sent, artifact = narrated.seen[-1]
    assert sent.to_json() == selection and artifact.text_path.read_bytes() == "你好 <&>".encode()
    assert artifact.directory == jobs.directory(speech["jobId"]) / "result"
    result = jobs.directory(with_narration["jobId"]) / "result"
    assert (result / "narration.txt").read_bytes() == "你好 <&>".encode()
    expected_sha = hashlib.sha256((result / "narration.txt").read_bytes()).hexdigest()
    link = with_narration["artifact"]
    assert (
        link["narrationTextUrl"] == f"/api/creation/jobs/{with_narration['jobId']}/narration-text"
    )
    assert link["narrationTextSha256"] == expected_sha
    text = CreationJobs(jobs.repository).narration_text(with_narration["jobId"])
    assert text.path.read_bytes() == (result / "narration.txt").read_bytes()
    assert text.sha256 == expected_sha and text.content_type.startswith("text/plain")
    receipt = jobs.read(result / "receipt.json")
    assert receipt["narration"]["licenseStatus"] == "unknown"
    assert receipt["narration"]["selection"] == selection
    # A render after removal carries no narration, and its text endpoint refuses.
    plain = render(removed["jobId"], "f")
    assert plain["status"] == "completed" and "narrationTextUrl" not in plain["artifact"]
    assert narrated.seen[-1] == (None, None)
    with pytest.raises(ValueError):
        jobs.narration_text(plain["jobId"])
    with pytest.raises(ValueError):
        jobs.narration_text(speech["jobId"])
    # Receipt forgeries on a completed render fail closed.
    for edit in (
        lambda r: r.pop("narration"),
        lambda r: r["narration"].update(startSample=1),
        lambda r: r["files"].pop("narration.txt"),
    ):
        receipt_path = result / "receipt.json"
        original = receipt_path.read_bytes()
        forged = json.loads(original)
        edit(forged)
        receipt_path.write_text(json.dumps(forged))
        state = jobs.read(jobs.directory(with_narration["jobId"]) / "status.json")
        state["resultReceiptSha256"] = hash_file(receipt_path)
        jobs.save(jobs.directory(with_narration["jobId"]) / "status.json", state)
        assert jobs.get(with_narration["jobId"])["status"] == "failed"
        receipt_path.write_bytes(original)
        state["resultReceiptSha256"] = hash_file(receipt_path)
        jobs.save(jobs.directory(with_narration["jobId"]) / "status.json", state)
        assert jobs.get(with_narration["jobId"])["status"] == "completed"
    forged = json.loads((result / "receipt.json").read_bytes())
    plain_receipt = jobs.directory(plain["jobId"]) / "result/receipt.json"
    plain_value = json.loads(plain_receipt.read_bytes())
    plain_value["narration"] = forged["narration"]
    plain_receipt.write_text(json.dumps(plain_value))
    state = jobs.read(jobs.directory(plain["jobId"]) / "status.json")
    state["resultReceiptSha256"] = hash_file(plain_receipt)
    jobs.save(jobs.directory(plain["jobId"]) / "status.json", state)
    assert jobs.get(plain["jobId"])["status"] == "failed"


def test_http_voices_generation_files_cancel_and_render_text(narrated):
    jobs = narrated.jobs
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(route, value):
        return urlopen(
            Request(
                base + route,
                json.dumps(value).encode(),
                {"Content-Type": "application/json", "Origin": base},
            ),
            timeout=30,
        )

    def get(route):
        with urlopen(base + route, timeout=30) as response:
            return response.read(), response.headers

    try:
        body, _ = get("/api/creation/voices")
        assert json.loads(body) == {
            "voices": [{"voiceId": "v1", "description": "Fixture 中文", "language": "804"}],
            "licenseStatus": "unknown",
        }
        with pytest.raises(HTTPError):
            get("/api/creation/voices?voice=v1")
        request = {
            "requestId": "a1" * 16,
            "projectId": "artifacts/project",
            "text": "网络旁白",
            "voiceId": "v1",
        }
        with post("/api/creation/narrations", request) as response:
            assert response.status == 202
            accepted = json.load(response)
        assert accepted["kind"] == "narration"
        state = finish(server.creation_jobs, accepted["jobId"])
        assert state["status"] == "completed"
        remote = json.loads(get(f"/api/creation/jobs/{accepted['jobId']}")[0])
        assert remote["narrationAsset"] == state["narrationAsset"]
        wav, headers = get(remote["narrationAsset"]["audioUrl"])
        assert headers["Content-Type"] == "audio/wav" and wav[:4] == b"RIFF"
        assert hashlib.sha256(wav).hexdigest() == hash_file(
            jobs.directory(accepted["jobId"]) / "result/narration.wav"
        )
        text, headers = get(remote["narrationAsset"]["textUrl"])
        assert text == "网络旁白".encode() and headers["Content-Type"].startswith("text/plain")
        for bad in ("receipt.json", "..%2Freceipt.json"):
            with pytest.raises(HTTPError):
                get(f"/api/creation/jobs/{accepted['jobId']}/narration-files/{bad}")
        with pytest.raises(HTTPError):
            get(remote["narrationAsset"]["audioUrl"] + "?path=outside")
        with post("/api/creation/narration-cancel", {"jobId": accepted["jobId"]}) as response:
            assert json.load(response)["cancelRequested"] is False
        for bad_body in ({}, {"jobId": accepted["jobId"], "x": 1}, {"jobId": "../x"}):
            with pytest.raises(HTTPError):
                post("/api/creation/narration-cancel", bad_body)
        with pytest.raises(HTTPError):
            post("/api/creation/narrations", {**request, "requestId": "b2" * 16, "path": "x"})
        selection = choice(state, start=1, gain=0, duck="off")
        revision = {**payload(jobs, narrated.root), "narration": selection}
        with post("/api/creation/revisions", revision) as response:
            revised = json.load(response)["jobId"]
        assert finish(server.creation_jobs, revised)["status"] == "completed"
        edit = json.loads(get(f"/api/creation/jobs/{revised}/edit?planId=hook-first")[0])
        assert edit["narration"] == selection and edit["narrationAsset"] == remote["narrationAsset"]
        rendered = {"requestId": "c3" * 16, "revisionJobId": revised, "width": 320, "height": 180}
        with post("/api/creation/renders", rendered) as response:
            render_id = json.load(response)["jobId"]
        done_render = finish(server.creation_jobs, render_id)
        assert done_render["status"] == "completed", done_render
        link = done_render["artifact"]["narrationTextUrl"]
        text, headers = get(link)
        assert text == "网络旁白".encode() and "attachment" in headers["Content-Disposition"]
        with pytest.raises(HTTPError):
            get(link + "?x=1")
        with pytest.raises(HTTPError):
            get(f"/api/creation/jobs/{narrated.root}/narration-text")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
