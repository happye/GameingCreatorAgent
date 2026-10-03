# Phase 0: semantic retrieval feasibility

Status: proposed scope, pending F000 technical review. Source: product plan sections 58–59 and 69–71.

## Goal

Given a local game video, create a `Video Semantic Timeline` and return timestamped clips for a natural-language query. The prototype is a developer-facing CLI. Do not build the desktop UI, publishing flow, billing, or a general video editor in this phase.

## Required behavior

1. Accept a local video path and validate that it is readable. Keep full video files on the user's machine.
2. Extract enough visual and audio evidence to identify gameplay events, while retaining timestamps and source references.
3. Persist semantic events and analysis metadata in SQLite; keep large media in the file system.
4. Expose model work behind replaceable provider interfaces. Record provider, model, prompt version, token usage, estimated cost, and processing time.
5. Search for a clearly described game mechanic and return ranked clips with start/end timecodes and relevance evidence.
6. Run a repeatable benchmark using representative, human-labeled clips.

## Go / no-go

For clear game-mechanic queries, at least 70% of the top ten returned clips must be judged usable or highly relevant by a human reviewer. Report the number of queries, labels, misses, runtime, and model cost. If the target fails, improve video understanding or retrieval before starting the UI.

The first feature, F000, is a reverse review of feasibility, model capability, video processing, cost, architecture, and one-person maintenance. Its conclusions may revise this scope before coding.
