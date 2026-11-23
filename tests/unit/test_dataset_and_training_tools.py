"""Unit tests for dataset collection and auto-labeling tools."""

import os
import shutil
import pytest

from src.tools.auto_labeler import (
    LABEL_LYING_LATERAL,
    LABEL_LYING_STERNAL,
    LABEL_MOUNTING,
    LABEL_STANDING,
    classify_cattle_bbox,
)
from src.tools.dataset_collector import get_time_category
from src.tools.train_yolo import prepare_dataset_structure


def test_classify_cattle_bbox_postures():
    # 1. 기립: w=100, h=120 (aspect ratio < 1.25)
    standing_box = [10.0, 10.0, 110.0, 130.0]
    assert classify_cattle_bbox(standing_box, [standing_box]) == LABEL_STANDING

    # 2. 흉와 (정상 엎드림): w=200, h=120 (aspect ratio ~ 1.66)
    sternal_box = [10.0, 10.0, 210.0, 130.0]
    assert classify_cattle_bbox(sternal_box, [sternal_box]) == LABEL_LYING_STERNAL

    # 3. 측와 (기립불능): w=300, h=100 (aspect ratio 3.0 > 2.3)
    lateral_box = [10.0, 10.0, 310.0, 110.0]
    assert classify_cattle_bbox(lateral_box, [lateral_box]) == LABEL_LYING_LATERAL

    # 4. 승가 (Mounting): 세로로 길쭉(h > w*1.3)하고 다른 소와 겹침
    cow_bottom = [100.0, 100.0, 200.0, 180.0]
    cow_top = [110.0, 50.0, 190.0, 160.0]  # w=80, h=110 -> h/w=1.375
    assert classify_cattle_bbox(cow_top, [cow_bottom, cow_top]) == LABEL_MOUNTING


def test_get_time_category_returns_valid_string():
    cat = get_time_category()
    assert cat in ["morning", "day", "evening", "night_ir"]


def test_prepare_dataset_structure(tmp_path):
    raw_dir = tmp_path / "raw"
    labels_dir = tmp_path / "labels"
    out_dir = tmp_path / "yolo_ds"

    raw_dir.mkdir()
    labels_dir.mkdir()

    # 5쌍의 더미 파일 생성
    for i in range(5):
        (raw_dir / f"img_{i}.jpg").write_text("dummy", encoding="utf-8")
        (labels_dir / f"img_{i}.txt").write_text("0 0.5 0.5 0.2 0.2", encoding="utf-8")

    yaml_path = prepare_dataset_structure(
        raw_images_dir=str(raw_dir),
        labels_dir=str(labels_dir),
        dataset_root=str(out_dir),
        train_ratio=0.8,
    )

    assert os.path.exists(yaml_path)
    assert os.path.exists(out_dir / "images" / "train")
    assert os.path.exists(out_dir / "images" / "val")
    # 5장 중 80%인 4장은 train, 1장은 val
    train_count = len(list((out_dir / "images" / "train").glob("*.jpg")))
    val_count = len(list((out_dir / "images" / "val").glob("*.jpg")))
    assert train_count == 4
    assert val_count == 1
