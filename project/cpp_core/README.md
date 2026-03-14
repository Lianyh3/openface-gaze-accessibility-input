# cpp_core (M0-M3 C++ Runtime Core)

This folder freezes cross-language runtime contracts for the planned
`C++ core + Python orchestration` architecture.

## Frozen M0 Types

1. `FrameFeatures`:
   raw frame-level features from OpenFace stream.
2. `GazePoint`:
   normalized gaze coordinate with hit-test target id.
3. `TargetEvent`:
   dwell-triggered event emitted to orchestration layer.

Header location:

- `include/gaze_core/contracts.h`

Backward-compatible shim for older includes:

- `include/gaze_core/contracts.hpp`

Python mirror implementation:

- `src/gaze_mvp/runtime_contract.py`

Validation command:

```bash
bash /home/lyh/workspace/run.sh m0-check
```

Optional C++ smoke compile:

```bash
cd /home/lyh/workspace/project/cpp_core
g++ -std=c++17 -Iinclude src/checks/contract_smoke.cpp -o /tmp/contract_smoke
/tmp/contract_smoke
```

## M1 Core (C++)

Implemented in header-only `.hpp` style:

- `include/gaze_core/runtime/m1.hpp`
- `src/apps/m1_runtime_replay.cpp`

Alignment check command:

```bash
bash /home/lyh/workspace/run.sh m1-check
```

## M2 Core (C++)

Implemented in header-only `.hpp` style:

- `include/gaze_core/runtime/m2.hpp`
- `src/apps/m2_runtime_replay.cpp`

Alignment check command:

```bash
bash /home/lyh/workspace/run.sh m2-check
```

## M3 Bridge (Current)

Current integration mode is a pragmatic bridge:

1. C++ M1 replay binary emits `TargetEvent` list.
2. Python orchestration consumes the events and drives keyboard flow.

Run command:

```bash
bash /home/lyh/workspace/run.sh gaze-cpp
```
