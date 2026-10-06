# Bundled models

| File | What | Source | License |
|---|---|---|---|
| `u2netp.onnx` (4.6 MB) | U²-Net-P salient object detection (the small U²-Net) | Qin et al., *U²-Net: Going Deeper with Nested U-Structure for Salient Object Detection*, Pattern Recognition 2020 — https://github.com/xuebinqin/U-2-Net ; ONNX export from https://github.com/danielgatis/rembg/releases/tag/v0.0.0 | Apache-2.0 |

SHA-256 `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8`.
Runs locally with `onnxruntime` (CPU, ~0.2 s per photo). If the file or onnxruntime is missing,
`engine/subject.py` falls back to classical colour-contrast saliency.
