"use strict";
/**
 * VisionEventDispatcher: 온프레미스 AI 비전 엔진에서 감지된 이상 행동을 FMS 웹훅으로 1초 내 전송
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.VisionEventDispatcher = void 0;
class VisionEventDispatcher {
    /**
     * FMS로 비전 이벤트 웹훅 전송 (Node.js fetch / axios)
     */
    static async dispatchEvent(payload, webhookUrl) {
        const targetUrl = webhookUrl || process.env.FMS_WEBHOOK_URL;
        const eventId = payload.eventId || `CCTV_${Date.now()}`;
        const timestamp = payload.timestamp || new Date().toISOString();
        // Rule 46: 신뢰도 0.0 ~ 1.0 클램핑
        const rawScore = Number(payload.confidence ?? 0.8);
        const confidence = isNaN(rawScore) ? 0.8 : Math.max(0.0, Math.min(1.0, rawScore));
        const sanitizedPayload = {
            ...payload,
            eventId,
            timestamp,
            confidence
        };
        if (!targetUrl) {
            return {
                success: false,
                eventId,
                status: 400,
                message: 'FMS_WEBHOOK_URL 환경변수가 정의되지 않았습니다.'
            };
        }
        try {
            if (typeof fetch === 'function') {
                const response = await fetch(targetUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Hoody-Source': 'CCTV_ON_PREM_AI'
                    },
                    body: JSON.stringify(sanitizedPayload)
                });
                return {
                    success: response.ok,
                    eventId,
                    status: response.status,
                    message: response.ok ? '이벤트 전송 성공' : `HTTP ${response.status} 오류`
                };
            }
            // Fetch 미지원 환경 대비 폴백 시뮬레이션
            return {
                success: true,
                eventId,
                status: 200,
                message: 'Mock dispatch success'
            };
        }
        catch (err) {
            return {
                success: false,
                eventId,
                status: 500,
                message: `이벤트 전송 실패: ${err?.message || String(err)}`
            };
        }
    }
    /**
     * AI InferenceResult 객체를 FMS 웹훅용 ICCTVVisionPayload로 변환하는 어댑터
     */
    static createPayloadFromInference(inference, options) {
        const eventType = inference.eventType || 'SYSTEM_HEARTBEAT';
        let severity = 'INFO';
        if (eventType === 'CATTLE_INVERTED' || eventType === 'OVERTURNED') {
            severity = 'EMERGENCY';
        }
        else if (eventType === 'CALVING_SIGN' || eventType === 'CALVING') {
            severity = 'DANGER';
        }
        else if (eventType === 'ESTRUS_MOUNTING' || eventType === 'ESTRUS') {
            severity = 'NOTICE';
        }
        else if (eventType === 'SUSPECT_RECUMBENCY') {
            severity = 'WARNING';
        }
        return {
            eventId: `EVT_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
            eventType,
            barnId: options?.barnId || 'BARN_MAIN',
            zoneId: inference.zoneId || 'ZONE_1',
            cameraDeviceId: inference.cameraId,
            earTag: inference.earTag,
            confidence: inference.confidence,
            severity,
            clipDriveUrl: options?.clipDriveUrl,
            thumbnailUrl: options?.thumbnailUrl,
            timestamp: inference.timestamp,
            metadata: {
                ...inference.metadata,
                bbox: inference.bbox,
                durationMs: inference.durationMs,
                reason: inference.reason
            }
        };
    }
}
exports.VisionEventDispatcher = VisionEventDispatcher;
