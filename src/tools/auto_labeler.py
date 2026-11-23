"""Automated Pseudo-Labeler for Cattle Behavior Detection.

Reads captured raw frames, detects cattle using baseline YOLO11n,
and auto-classifies postures (standing, lying_sternal, lying_lateral, mounting)
generating standard YOLO format TXT label files.
"""

import argparse
import glob
import os
from typing import Dict, List, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

# 4개 행동인식 클래스 정의
LABEL_STANDING = 0       # 기립 (서 있음)
LABEL_LYING_STERNAL = 1  # 흉와 (정상 엎드림)
LABEL_LYING_LATERAL = 2  # 측와 (옆으로 누움 / 기립불능)
LABEL_MOUNTING = 3       # 승가 (발정 행위)

CLASS_NAMES = {
    LABEL_STANDING: "standing",
    LABEL_LYING_STERNAL: "lying_sternal",
    LABEL_LYING_LATERAL: "lying_lateral",
    LABEL_MOUNTING: "mounting",
}


def classify_cattle_bbox(
    bbox: List[float],
    all_bboxes: List[List[float]],
) -> int:
    """Classify posture based on geometry and multi-cow overlap."""
    x1, y1, x2, y2 = bbox
    w = max(x2 - x1, 1.0)
    h = max(y2 - y1, 1.0)
    aspect_ratio = w / h

    # 1. 승가(Mounting) 판정: 세로로 길쭉하고(h > w) 다른 소 박스와 높은 세로 겹침이 있는 경우
    if h / w > 1.3:
        for other in all_bboxes:
            if other == bbox:
                continue
            ox1, oy1, ox2, oy2 = other
            # IoU 또는 교차 영역 확인
            inter_x1 = max(x1, ox1)
            inter_y1 = max(y1, oy1)
            inter_x2 = min(x2, ox2)
            inter_y2 = min(y2, oy2)
            if inter_x2 > inter_x1 and inter_y2 > inter_y1:
                return LABEL_MOUNTING

    # 2. 측와(기립불능) 판정: 바닥에 극단적으로 길게 누워 가로세로비 2.3 초과
    if aspect_ratio > 2.3:
        return LABEL_LYING_LATERAL

    # 3. 흉와(정상 엎드림) 판정: 가로로 누워있으나 등이 위로 솟아 있는 정상 휴식 (1.2 ~ 2.3)
    if aspect_ratio >= 1.25:
        return LABEL_LYING_STERNAL

    # 4. 기립(서 있음) 판정: 일반적인 서 있는 상태
    return LABEL_STANDING


def auto_label_dataset(
    image_dir: str = "datasets/raw_frames",
    output_label_dir: str = "datasets/labels",
    preview_dir: str = "datasets/annotated_preview",
    model_path: str = "yolo11n.pt",
    conf_thresh: float = 0.35,
) -> Dict[str, int]:
    """Generates YOLO TXT label files from raw images."""
    os.makedirs(output_label_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)

    model = YOLO(model_path)
    image_paths = glob.glob(os.path.join(image_dir, "*.jpg")) + glob.glob(os.path.join(image_dir, "*.png"))

    print("====================================================")
    print("🏷️ [후디팜 CCTV] 소 행동 반자동 의사 라벨러 (Auto-Labeler)")
    print(f"🖼️ 처리 대상 이미지: {len(image_paths)}장")
    print("====================================================")

    stats = {CLASS_NAMES[c]: 0 for c in CLASS_NAMES}
    total_images_processed = 0

    for idx, img_path in enumerate(image_paths, 1):
        frame = cv2.imread(img_path)
        if frame is None:
            continue

        img_h, img_w = frame.shape[:2]
        results = model(frame, verbose=False)
        boxes = results[0].boxes

        cow_boxes = []
        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            cls_name = model.names[cls_id]
            if cls_name == "cow" and conf >= conf_thresh:
                coords = [float(v) for v in box.xyxy[0].cpu().tolist()]
                cow_boxes.append(coords)

        # YOLO TXT 라벨 파일 생성
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        txt_path = os.path.join(output_label_dir, f"{base_name}.txt")

        preview_img = frame.copy()
        lines = []

        for bbox in cow_boxes:
            target_cls = classify_cattle_bbox(bbox, cow_boxes)
            stats[CLASS_NAMES[target_cls]] += 1

            x1, y1, x2, y2 = bbox
            # Normalize to 0~1
            xc = ((x1 + x2) / 2.0) / img_w
            yc = ((y1 + y2) / 2.0) / img_h
            bw = (x2 - x1) / img_w
            bh = (y2 - y1) / img_h
            lines.append(f"{target_cls} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")

            # Preview box drawing
            color = (0, 255, 0)
            if target_cls == LABEL_LYING_LATERAL:
                color = (0, 0, 255)  # Red for lateral (critical)
            elif target_cls == LABEL_MOUNTING:
                color = (255, 0, 255)  # Purple for mounting
            elif target_cls == LABEL_LYING_STERNAL:
                color = (255, 200, 0)  # Cyan for sternal

            cv2.rectangle(preview_img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(
                preview_img,
                f"{CLASS_NAMES[target_cls]}",
                (int(x1), max(15, int(y1) - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # Save first 30 preview images for human quality inspection
        if idx <= 30:
            cv2.imwrite(os.path.join(preview_dir, f"preview_{base_name}.jpg"), preview_img)

        total_images_processed += 1

    print("\n✅ 라벨 생성 완료!")
    print(f"📊 총 이미지: {total_images_processed}장")
    for k, v in stats.items():
        print(f"  - {k}: {v}건")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HoodyFarm Cattle Behavior Auto-Labeler")
    parser.add_argument("--img-dir", default="datasets/raw_frames", help="Raw images directory")
    parser.add_argument("--out-dir", default="datasets/labels", help="Labels output directory")
    args = parser.parse_args()

    auto_label_dataset(image_dir=args.img_dir, output_label_dir=args.out_dir)
