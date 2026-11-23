"""Fine-tuning pipeline for YOLO11n Cattle Behavior Detection.

Splits dataset into train/val, writes cattle_dataset.yaml,
and executes Ultralytics YOLO fine-tuning.
"""

import argparse
import glob
import os
import random
import shutil
from typing import Dict, List

import yaml
from ultralytics import YOLO


def prepare_dataset_structure(
    raw_images_dir: str = "datasets/raw_frames",
    labels_dir: str = "datasets/labels",
    dataset_root: str = "datasets/yolo_dataset",
    train_ratio: float = 0.8,
) -> str:
    """Prepares standard YOLO dataset folder hierarchy (images/train, labels/train, etc.)."""
    for split in ["train", "val"]:
        os.makedirs(os.path.join(dataset_root, "images", split), exist_ok=True)
        os.makedirs(os.path.join(dataset_root, "labels", split), exist_ok=True)

    img_files = glob.glob(os.path.join(raw_images_dir, "*.jpg")) + glob.glob(os.path.join(raw_images_dir, "*.png"))
    valid_pairs = []

    for img_path in img_files:
        base = os.path.splitext(os.path.basename(img_path))[0]
        label_path = os.path.join(labels_dir, f"{base}.txt")
        if os.path.exists(label_path):
            valid_pairs.append((img_path, label_path))

    if not valid_pairs:
        raise RuntimeError("No matching image/label pairs found in datasets/")

    random.seed(42)
    random.shuffle(valid_pairs)

    split_idx = int(len(valid_pairs) * train_ratio)
    train_pairs = valid_pairs[:split_idx]
    val_pairs = valid_pairs[split_idx:]

    for pair, split in [(train_pairs, "train"), (val_pairs, "val")]:
        for img, lbl in pair:
            shutil.copy2(img, os.path.join(dataset_root, "images", split, os.path.basename(img)))
            shutil.copy2(lbl, os.path.join(dataset_root, "labels", split, os.path.basename(lbl)))

    yaml_path = os.path.join(dataset_root, "cattle_behavior.yaml")
    data_dict = {
        "path": os.path.abspath(dataset_root).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "names": {
            0: "standing",
            1: "lying_sternal",
            2: "lying_lateral",
            3: "mounting",
        },
    }

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data_dict, f, default_flow_style=False)

    print(f"✅ 데이터셋 준비 완료: 학습용 {len(train_pairs)}장, 검증용 {len(val_pairs)}장")
    print(f"📄 설정 파일: {yaml_path}")
    return yaml_path


def train_cattle_model(
    data_yaml: str,
    base_model: str = "yolo11n.pt",
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 16,
    device: str = "cpu",
    output_model_path: str = "models/yolo11n_cattle_behavior.pt",
) -> str:
    """Executes YOLO11n fine-tuning."""
    print("====================================================")
    print("🚀 [후디팜 CCTV] YOLO11n 소 행동인식 모델 파인튜닝 가동")
    print(f"📦 베이스 모델: {base_model}")
    print(f"📊 에폭: {epochs} / 배치크기: {batch} / 디바이스: {device}")
    print("====================================================")

    model = YOLO(base_model)
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project="runs/detect",
        name="cattle_behavior",
        exist_ok=True,
    )

    # Export best model
    best_weight = os.path.join("runs", "detect", "cattle_behavior", "weights", "best.pt")
    if os.path.exists(best_weight):
        os.makedirs(os.path.dirname(output_model_path), exist_ok=True)
        shutil.copy2(best_weight, output_model_path)
        print(f"\n🎉 파인튜닝 완료! 최종 가중치 저장: {output_model_path}")
        return output_model_path
    else:
        print("\n⚠️ 학습 완료되었으나 best.pt 경로를 확인해주세요.")
        return base_model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HoodyFarm Cattle Behavior Model Trainer")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--device", default="cpu", help="Device to use (cpu or 0 for GPU)")
    parser.add_argument("--prepare-only", action="store_true", help="Only prepare dataset structure")
    args = parser.parse_args()

    yaml_file = prepare_dataset_structure()
    if not args.prepare_only:
        train_cattle_model(data_yaml=yaml_file, epochs=args.epochs, batch=args.batch, device=args.device)
