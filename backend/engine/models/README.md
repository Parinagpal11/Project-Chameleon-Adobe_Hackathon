# Bundled models

| File | What | Source | License |
|---|---|---|---|
| `u2netp.onnx` (4.6 MB) | U²-Net-P salient object detection (the small U²-Net) | Qin et al., *U²-Net: Going Deeper with Nested U-Structure for Salient Object Detection*, Pattern Recognition 2020 — https://github.com/xuebinqin/U-2-Net ; ONNX export from https://github.com/danielgatis/rembg/releases/tag/v0.0.0 | Apache-2.0 |

| `yolox_nano.onnx` (3.6 MB) | YOLOX-Nano object detector (COCO); only its *person* class is used, to find people the face and salient-object steps miss (a group in a row, people in a busy market) | Ge et al., *YOLOX: Exceeding YOLO Series in 2021* — https://github.com/Megvii-BaseDetection/YOLOX , release 0.1.1rc0 `yolox_nano.onnx` | Apache-2.0 |

| `face_detection_yunet_2023mar.onnx` (0.2 MB) | YuNet face detector; used only for faces that fill most of the frame (beauty close-ups), which the Haar detector misses. The eyes, nose and mouth from its landmarks become the subject | Wu et al., *YuNet: A Tiny Millisecond-level Face Detector*, Machine Intelligence Research 2023 — https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet | MIT |

SHA-256 `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8` (u2netp),
`c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d` (yolox_nano),
`8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` (YuNet, run with OpenCV's `FaceDetectorYN`).
Runs locally with `onnxruntime` (CPU, ~0.2 s per photo). If the file or onnxruntime is missing,
`engine/subject.py` falls back to classical colour-contrast saliency.
