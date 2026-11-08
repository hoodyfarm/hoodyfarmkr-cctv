"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FmsEmergencyDispatcher = void 0;
/**
 * FmsEmergencyDispatcher: 온프레미스 AI 감지 이벤트를 FMS로 전송하는 1초 긴급 웹훅 디스패처
 * - 30분 쿨다운 스로틀링:
 *   동일 우방/축사/카메라(barnId 또는 cameraId) + 동일 eventType의 알림 중복 방지 (Deduplication)
 * - Two-Stage 비동기 디스패치 파이프라인 정착:
 *   - Stage 1: 감지 즉시 FMS `APP_ingestCameraEvent`로 JSON 웹훅 송신 (isPreliminary: true)
 *   - Stage 2: 숏클립 클라우드 업로드 완료 후 비디오 URL 패치 웹훅 송신 (isPreliminary: false)
 * - Rule 46 신뢰도 클램핑 및 타임아웃 방어
 */
class FmsEmergencyDispatcher {
    webhookUrl;
    cooldownMs;
    timeoutMs;
    httpFetch;
    // 30분 쿨다운 해시 테이블: key = `${targetId}_${eventType}` -> lastAlertTimeMs
    lastAlertTimestamps = new Map();
    constructor(options) {
        this.webhookUrl = options?.webhookUrl || process.env.FMS_WEBHOOK_URL || 'https://fms.hoodyfarm.com/api/cctv/webhook';
        this.cooldownMs = (options?.cooldownMinutes ?? 30) * 60 * 1000;
        this.timeoutMs = options?.timeoutMs ?? 3000;
        this.httpFetch = options?.httpFetch;
    }
    /**
     * 쿨다운 키 생성: targetId(barnId 또는 cameraId) + eventType
     */
    getCooldownKey(targetId, eventType) {
        const safeTarget = String(targetId || 'DEFAULT_BARN').trim();
        const safeType = String(eventType || 'ABNORMAL_BEHAVIOR').trim().toUpperCase();
        return `${safeTarget}_${safeType}`;
    }
    /**
     * 긴급 이벤트 디스패치 (Stage 1: 0.5초 즉시 경보 또는 Stage 2: 비디오 패치)
     */
    async dispatchEmergency(payload) {
        const eventType = this.normalizeEventType(payload.eventType);
        const cameraId = payload.cameraId || 'CAM_DEFAULT';
        // barnId가 명시되지 않은 경우 cameraId를 barnId로 활용하거나 zoneId 활용
        const barnId = payload.barnId || (payload.zoneId && payload.zoneId !== 'MAIN_BARN' ? payload.zoneId : cameraId);
        const zoneId = payload.zoneId || barnId;
        const eventId = payload.eventId || `EVT_${Date.now()}`;
        const stage = payload.stage || 'STAGE1_INSTANT';
        const isPreliminary = payload.isPreliminary !== undefined
            ? payload.isPreliminary
            : (stage === 'STAGE1_INSTANT');
        const now = Date.now();
        // 1. 30분 쿨다운 검사: 동일 barnId(또는 cameraId) + eventType
        // Stage 1 긴급 알림(isPreliminary: true)에만 쿨다운 적용, Stage 2 비디오 패치(isPreliminary: false)는 항상 허용
        const cooldownKey = this.getCooldownKey(barnId, eventType);
        if (stage === 'STAGE1_INSTANT' && isPreliminary) {
            const lastSent = this.lastAlertTimestamps.get(cooldownKey) || 0;
            if (now - lastSent < this.cooldownMs) {
                return {
                    success: true,
                    eventId,
                    status: 200,
                    message: `[쿨다운 스로틀링] 동일 축사/우방(${barnId}) ${eventType} 알림이 ${Math.ceil((this.cooldownMs - (now - lastSent)) / 60000)}분 잔여로 중복 발송을 생략합니다.`,
                    throttled: true
                };
            }
        }
        // 2. Rule 46: 신뢰도 클램핑 (0.0 ~ 1.0)
        const rawConf = Number(payload.confidence ?? 0.85);
        const confidence = isNaN(rawConf) ? 0.85 : Math.max(0.0, Math.min(1.0, rawConf));
        // 3. 심각도(Severity) 자동 결정
        const severity = this.resolveSeverity(eventType, payload.severity);
        // FMS `APP_ingestCameraEvent` 및 CameraVisionService와 100% 호환되는 정규화 페이로드
        const sanitizedPayload = {
            action: 'ingestCameraEvent',
            eventId,
            eventType,
            barnId,
            cameraId,
            cameraDeviceId: cameraId,
            zoneId,
            earTag: payload.earTag,
            confidence,
            severity,
            timestamp: payload.timestamp || new Date().toISOString(),
            snapshotBase64: payload.snapshotBase64,
            thumbnailUrl: payload.thumbnailUrl || (payload.snapshotBase64 ? `data:image/jpeg;base64,${payload.snapshotBase64}` : undefined),
            videoUrl: payload.videoUrl,
            clipDriveUrl: payload.clipDriveUrl || payload.videoUrl,
            stage,
            isPreliminary,
            metadata: payload.metadata
        };
        // 4. HTTP 웹훅 전송 (타임아웃 방어 포함)
        const fetchFn = this.httpFetch || (typeof fetch === 'function' ? fetch : undefined);
        if (!fetchFn) {
            // Fetch 미지원 또는 순수 로컬 Mock 환경
            if (stage === 'STAGE1_INSTANT' && isPreliminary) {
                this.lastAlertTimestamps.set(cooldownKey, now);
            }
            return {
                success: true,
                eventId,
                status: 200,
                message: 'Mock HTTP 디스패치 성공'
            };
        }
        try {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), this.timeoutMs);
            const response = await fetchFn(this.webhookUrl, {
                method: stage === 'STAGE2_VIDEO_PATCH' ? 'PATCH' : 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Hoody-Source': 'CCTV_VISION_AI'
                },
                body: JSON.stringify(sanitizedPayload),
                signal: controller.signal
            });
            clearTimeout(timer);
            if (response.ok) {
                if (stage === 'STAGE1_INSTANT' && isPreliminary) {
                    this.lastAlertTimestamps.set(cooldownKey, now);
                }
                return {
                    success: true,
                    eventId,
                    status: response.status,
                    message: `${stage} 웹훅 전송 성공`
                };
            }
            else {
                return {
                    success: false,
                    eventId,
                    status: response.status,
                    message: `HTTP ${response.status} 오류`
                };
            }
        }
        catch (err) {
            const isTimeout = err?.name === 'AbortError';
            return {
                success: false,
                eventId,
                status: isTimeout ? 408 : 500,
                message: isTimeout ? `웹훅 타임아웃 (${this.timeoutMs}ms 초과)` : `웹훅 전송 예외: ${err?.message || String(err)}`
            };
        }
    }
    /**
     * 이벤트 타입 정규화 (별칭 호환)
     */
    normalizeEventType(type) {
        switch (type) {
            case 'OVERTURNED':
            case 'CATTLE_INVERTED':
                return 'OVERTURNED';
            case 'CALVING':
            case 'CALVING_SIGN':
                return 'CALVING';
            case 'ESTRUS':
            case 'ESTRUS_MOUNTING':
                return 'ESTRUS';
            case 'SUSPECT_RECUMBENCY':
                return 'SUSPECT_RECUMBENCY';
            default:
                return 'SYSTEM_HEARTBEAT';
        }
    }
    resolveSeverity(type, fallback) {
        if (fallback)
            return fallback;
        switch (type) {
            case 'OVERTURNED':
                return 'EMERGENCY'; // 소 뒤집힘은 최상위 비상
            case 'CALVING':
                return 'DANGER'; // 분만 징후
            case 'SUSPECT_RECUMBENCY':
                return 'WARNING'; // 의심 와복
            case 'ESTRUS':
                return 'NOTICE'; // 발정
            default:
                return 'INFO';
        }
    }
    /**
     * 쿨다운 상태 초기화 (테스트용)
     */
    resetCooldowns() {
        this.lastAlertTimestamps.clear();
    }
    getCooldownRemainingMs(targetId, eventType) {
        const key = this.getCooldownKey(targetId, eventType);
        const last = this.lastAlertTimestamps.get(key) || 0;
        const diff = Date.now() - last;
        return Math.max(0, this.cooldownMs - diff);
    }
}
exports.FmsEmergencyDispatcher = FmsEmergencyDispatcher;
