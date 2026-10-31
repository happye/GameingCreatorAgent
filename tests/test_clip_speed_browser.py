"""Clip speed editor behavior with saved version and source-clock assertions."""

from test_creation_editing_browser import test_editing_version_flows as run_editing_flow


def test_clip_speed_saved_versions():
    run_editing_flow("speed")
