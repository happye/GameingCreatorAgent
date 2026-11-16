"""A stale narration gesture must release its global Escape listener without pointerup."""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("invalidate", ["undo", "gain", "scope"])
def test_stale_narration_drag_cleans_before_unmount(invalidate):
    source = (
        Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/studio/multitrack.js"
    )
    script = r"""
const fs = require('fs'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
const extract = (name, next) => source.slice(source.indexOf('function ' + name), source.indexOf('function ' + next));
const globalTarget = new EventTarget();
global.addEventListener = globalTarget.addEventListener.bind(globalTarget);
global.removeEventListener = globalTarget.removeEventListener.bind(globalTarget);
eval(extract('narrationGestureMatches', 'useTrackWidth'));
eval(extract('bindNarrationDrag', 'useNarrationGesture'));
let drag;
const current = {editEpoch: 1, assetJobId: 'asset', receiptSha256: 'sha', status: 'ready', onMove() {throw new Error('stale commit');}};
const narrationMoveRef = {current}, scopeRef = {current: 'one'}, cleanupRef = {current: null};
const handle = new EventTarget();
handle.releasePointerCapture = () => { handle.dispatchEvent(new Event('lostpointercapture')); };
bindNarrationDrag({preventDefault(){}, stopPropagation(){}, currentTarget: handle, pointerId: 1, clientX: 10},
 {narrationMove: current, narrationMoveRef, scope: 'one', scopeRef, scale: 1, fps: 30,
 maxStart: () => 100, setDrag: value => {drag = value;}, cleanupRef});
if (process.argv[2] === 'scope') scopeRef.current = 'two';
else narrationMoveRef.current = {...current, editEpoch: 2};
handle.dispatchEvent(new Event('pointermove'));
assert.equal(drag, null);
assert.equal(cleanupRef.current, null);
// Simulate unmount with no further pointerup; old listener must not consume Escape.
cleanupRef.current?.();
const key = new Event('keydown', {cancelable: true});
key.key = 'Escape';
globalTarget.dispatchEvent(key);
assert.equal(key.defaultPrevented, false);
"""
    result = subprocess.run(
        ["node", "-e", script, str(source), invalidate], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
