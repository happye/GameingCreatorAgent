"""Manifest publication waits only for bounded Windows sharing contention."""

import os
import time

import pytest
from test_benchmark_workflow_file_contention import held
from test_sqlite_store import bundle_fixture

from gamingcreator.application.media import SamplingParameters
from gamingcreator.infrastructure.ffmpeg_media import write_manifest


@pytest.mark.skipif(os.name != "nt", reason="Real Windows sharing semantics")
@pytest.mark.parametrize("release", [True, False])
def test_manifest_replace_waits_or_preserves_original(tmp_path, release):
    bundle = bundle_fixture(tmp_path)
    original = bundle.manifest_path.read_bytes()
    source = bundle.asset.source_path.read_bytes()
    with held(bundle.manifest_path, 1, release_after=0.2 if release else None):
        start = time.monotonic()
        if release:
            write_manifest(bundle, SamplingParameters())
        else:
            with pytest.raises(PermissionError):
                write_manifest(bundle, SamplingParameters())
        assert (0.15 if release else 0.9) <= time.monotonic() - start < 3
    assert bundle.manifest_path.read_bytes() == original
    assert bundle.asset.source_path.read_bytes() == source
    assert bundle.manifest_path.with_suffix(".tmp").exists() is not release
