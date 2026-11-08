"use strict";
/**
 * InferenceEngine: 한우 3대 이상행동(기립불능, 분만 징후, 승가/발정) AI 비전 추론 파이프라인
 *
 * 저전력 N100 미니PC 및 온프레미스 에지 환경을 위해 설계:
 * 1) ONNX / YOLOv8n / OpenCV 경량 모델 인터페이스 연동
 * 2) 3대 이상행동 판별:
 *    - CATTLE_INVERTED: 기립불능 (등/다리 반전, 비정상 누움 지속 3분 이상)
 *    - CALVING_SIGN: 분만 징후 (양수 파열, 잦은 기립/와모, 꼬리 들림 30초 이상)
 *    - ESTRUS_MOUNTING: 승가/발정 행위 (타 개체 탑승 행동 3초 이상)
 * 3) 안전 가드:
 *    - 단순 수면/휴식을 기립불능으로 오인하지 않도록 '지속 시간 임계치(기본 3분/180,000ms)' 필터 가드
 *    - 신뢰도(Confidence) 85% 이상 시만 이벤트 트리거 (Rule 46 신뢰도 클램핑)
 *    - 한 번 알림 트리거 후 무한 연발 방지 가드 (State Machine 관리)
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.InferenceEngine = void 0;
const visionEventDispatcher_1 = require("../visionEventDispatcher");
class InferenceEngine {
    confidenceThreshold;
    durationThresholdMs;
    calvingDurationThresholdMs;
    estrusDurationThresholdMs;
    modelType;
    customInferFn;
    // 행동 지속 시간 추적 상태 레지스트리: trackKey -> IBehaviorTrackState
    trackingStates = new Map();
    constructor(options, customInferFn) {
        this.modelType = options?.modelType || 'YOLOv8n';
        this.confidenceThreshold = options?.confidenceThreshold ?? 0.85; // 기본 85%
        this.durationThresholdMs = options?.durationThresholdMs ?? 180000; // 기립불능: 3분 (180,000ms)
        this.calvingDurationThresholdMs = options?.calvingDurationThresholdMs ?? 30000; // 분만: 30초
        this.estrusDurationThresholdMs = options?.estrusDurationThresholdMs ?? 3000; // 승가: 3초
        this.customInferFn = customInferFn;
    }
    /**
     * 커스텀 추론 함수 주입 (ONNX Runtime, OpenCV DNN, YOLO 가속기 바인딩용)
     */
    setModelInference(fn) {
        this.customInferFn = fn;
    }
    /**
     * 단일 프레임 추론 및 이상행동 지속 시간 가드 분석
     */
    async processFrame(frame) {
        const rawDetections = await this.runModelInference(frame);
        const results = [];
        const timestampMs = frame.timestampMs || Date.now();
        for (const detection of rawDetections) {
            const normalizedBehavior = this.normalizeBehaviorType(detection.label);
            if (!normalizedBehavior) {
                continue;
            }
            // Rule 46: 신뢰도 클램핑 (0.0 ~ 1.0)
            const rawConf = Number(detection.confidence);
            const confidence = isNaN(rawConf) ? 0.0 : Math.max(0.0, Math.min(1.0, rawConf));
            // 1. 신뢰도 85% 미만은 무시
            if (confidence < this.confidenceThreshold) {
                continue;
            }
            // 2. 개체/카메라별 지속 시간 추적 키 생성
            const earTag = detection.earTag || frame.earTag;
            const trackId = detection.trackId ? String(detection.trackId) : 'default';
            const entityId = earTag ? `tag_${earTag}` : `track_${trackId}`;
            const trackKey = `${frame.cameraId}_${entityId}_${normalizedBehavior}`;
            const thresholdRequired = this.getDurationThresholdForBehavior(normalizedBehavior);
            let track = this.trackingStates.get(trackKey);
            if (!track) {
                track = {
                    trackKey,
                    behaviorType: normalizedBehavior,
                    cameraId: frame.cameraId,
                    earTag,
                    firstDetectedMs: timestampMs,
                    lastDetectedMs: timestampMs,
                    consecutiveFrames: 1,
                    maxConfidence: confidence,
                    alertTriggered: false
                };
                this.trackingStates.set(trackKey, track);
            }
            else {
                // 이미 추적 중인 경우 갱신
                track.lastDetectedMs = timestampMs;
                track.consecutiveFrames += 1;
                track.maxConfidence = Math.max(track.maxConfidence, confidence);
            }
            const currentDurationMs = Math.max(0, track.lastDetectedMs - track.firstDetectedMs);
            // 3. 지속 시간 임계치 필터 가드 검증
            const isThresholdMet = currentDurationMs >= thresholdRequired;
            const shouldTrigger = isThresholdMet && !track.alertTriggered;
            if (shouldTrigger) {
                track.alertTriggered = true; // 1회 트리거 후 중복 방지
            }
            results.push({
                detected: true,
                eventTriggered: shouldTrigger,
                eventType: normalizedBehavior,
                confidence,
                durationMs: currentDurationMs,
                earTag,
                cameraId: frame.cameraId,
                zoneId: frame.zoneId,
                bbox: detection.bbox,
                timestamp: new Date(timestampMs).toISOString(),
                reason: shouldTrigger
                    ? `[트리거] ${normalizedBehavior} 신뢰도 ${(confidence * 100).toFixed(1)}% 및 지속시간 ${(currentDurationMs / 1000).toFixed(1)}s (기준 ${(thresholdRequired / 1000).toFixed(1)}s 이상)`
                    : `[가드 유지] 지속시간 ${(currentDurationMs / 1000).toFixed(1)}s < 기준 ${(thresholdRequired / 1000).toFixed(1)}s`,
                metadata: {
                    consecutiveFrames: track.consecutiveFrames,
                    thresholdRequiredMs: thresholdRequired,
                    modelType: this.modelType
                }
            });
        }
        return results;
    }
    /**
     * 프레임 처리와 동시에 이벤트 트리거 시 VisionEventDispatcher로 1초 웹훅 자동 디스패치
     */
    async processAndDispatch(frame, webhookUrl, extraOptions) {
        const results = await this.processFrame(frame);
        const dispatchedPayloads = [];
        for (const res of results) {
            if (res.eventTriggered && res.eventType) {
                const payload = visionEventDispatcher_1.VisionEventDispatcher.createPayloadFromInference(res, extraOptions);
                await visionEventDispatcher_1.VisionEventDispatcher.dispatchEvent(payload, webhookUrl);
                dispatchedPayloads.push(payload);
            }
        }
        return { results, dispatchedPayloads };
    }
    /**
     * 이상행동 해소/종료 시 상태 리셋 (예: 소가 다시 정상 기립하여 서있는 경우)
     */
    resetTrackState(cameraId, earTagOrTrackId, behaviorType) {
        if (!earTagOrTrackId && !behaviorType) {
            // 카메라 전체 리셋
            for (const [key, val] of this.trackingStates.entries()) {
                if (val.cameraId === cameraId) {
                    this.trackingStates.delete(key);
                }
            }
            return;
        }
        for (const [key, val] of this.trackingStates.entries()) {
            if (val.cameraId === cameraId) {
                const matchEntity = !earTagOrTrackId || key.includes(earTagOrTrackId);
                const matchBehavior = !behaviorType || val.behaviorType === behaviorType;
                if (matchEntity && matchBehavior) {
                    this.trackingStates.delete(key);
                }
            }
        }
    }
    /**
     * 전체 추적 상태 초기화 (테스트용)
     */
    clearAllTracks() {
        this.trackingStates.clear();
    }
    /**
     * 특정 키의 추적 상태 반환 (테스트 및 디버그용)
     */
    getTrackState(cameraId, entityId, behaviorType) {
        const key = `${cameraId}_${entityId}_${behaviorType}`;
        return this.trackingStates.get(key);
    }
    /**
     * 모델 추론 실행 (커스텀 함수 또는 온프레미스 경량 시뮬레이터)
     */
    async runModelInference(frame) {
        if (this.customInferFn) {
            return await this.customInferFn(frame);
        }
        // 기본 시뮬레이션: 프레임 버퍼가 없거나 별도 주입 없을 시 기본 빈 배열
        return [];
    }
    /**
     * 레이블 명칭을 표준 3대 이상행동 이벤트 타입으로 정규화
     */
    normalizeBehaviorType(label) {
        const upper = (label || '').toUpperCase();
        if (upper === 'CATTLE_INVERTED' || upper === 'OVERTURNED' || upper === 'INVERTED') {
            return 'CATTLE_INVERTED';
        }
        if (upper === 'CALVING_SIGN' || upper === 'CALVING' || upper === 'DELIVERY') {
            return 'CALVING_SIGN';
        }
        if (upper === 'ESTRUS_MOUNTING' || upper === 'ESTRUS' || upper === 'MOUNTING') {
            return 'ESTRUS_MOUNTING';
        }
        return null;
    }
    /**
     * 행동 유형별 안전 지속 시간 임계치(ms) 결정
     */
    getDurationThresholdForBehavior(type) {
        switch (type) {
            case 'CATTLE_INVERTED':
            case 'OVERTURNED':
                return this.durationThresholdMs; // 기립불능: 기본 3분 (수면/와복 오인 방어)
            case 'CALVING_SIGN':
            case 'CALVING':
                return this.calvingDurationThresholdMs; // 분만 징후: 기본 30초
            case 'ESTRUS_MOUNTING':
            case 'ESTRUS':
                return this.estrusDurationThresholdMs; // 승가/발정: 기본 3초
            default:
                return 0;
        }
    }
}
exports.InferenceEngine = InferenceEngine;
