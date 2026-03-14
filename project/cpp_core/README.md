# cpp_core (M0 Contract Freeze)

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

Python mirror implementation:

- `src/gaze_mvp/runtime_contract.py`

Validation command:

```bash
bash /home/lyh/workspace/run.sh m0-check
```

Optional C++ smoke compile:

```bash
cd /home/lyh/workspace/project/cpp_core
g++ -std=c++17 -Iinclude src/contracts.cpp src/contract_smoke.cpp -o /tmp/contract_smoke
/tmp/contract_smoke
```

## M1 Core (C++)

Implemented in `.h + .cpp` style:

- `include/gaze_core/runtime_m1.h`
- `src/runtime_m1.cpp`
- `src/m1_runtime_replay.cpp`

Alignment check command:

```bash
bash /home/lyh/workspace/run.sh m1-check
```
