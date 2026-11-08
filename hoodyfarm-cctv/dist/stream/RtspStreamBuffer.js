"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.RtspStreamBuffer = exports.ReconnectBackoffManager = exports.RtspUrlParser = void 0;
const fs_1 = __importDefault(require("fs"));
/**
 * Tuya 및 ONVIF 카메라 RTSP URL 유연 파서
 * - 표준 형식: rtsp://[user:pass@]host[:port]/path
 * - Tuya 특화 경로 지원 (/live/ch0, /onvif1, /Streaming/Channels/101 등)
 * - 환경변수 및 축약 설정 자동 정규화
 */
class RtspUrlParser {
    static parse(rawUrlOrConfig) {
        if (typeof rawUrlOrConfig === 'object') {
            const { cameraId = 'CAM_DEFAULT', streamUrl, username, password, host, port, path: urlPath } = rawUrlOrConfig;
            if (streamUrl && streamUrl.trim()) {
                return this.parseString(streamUrl.trim(), cameraId);
            }
            const userPart = username ? (password ? `${encodeURIComponent(username)}:${encodeURIComponent(password)}@` : `${encodeURIComponent(username)}@`) : '';
            const hostPart = host || '127.0.0.1';
            const portPart = port ? `:${port}` : ':554';
            const pathPart = urlPath ? (urlPath.startsWith('/') ? urlPath : `/${urlPath}`) : '/live/ch0';
            const fullUrl = `rtsp://${userPart}${hostPart}${portPart}${pathPart}`;
            return {
                cameraId,
                streamUrl: fullUrl,
                username,
                password,
                host: hostPart,
                port: port ? Number(port) : 554,
                path: pathPart
            };
        }
        return this.parseString(rawUrlOrConfig, 'CAM_DEFAULT');
    }
    static parseString(rawUrl, defaultCameraId) {
        const trimmed = rawUrl.trim();
        const regex = /^rtsp:\/\/(?:([^:]+)(?::([^@]+))?@)?([^:/]+)(?::(\d+))?(\/.*)?$/i;
        const match = trimmed.match(regex);
        if (!match) {
            // 비표준 URL에 대한 안전 기본 폴백
            return {
                cameraId: defaultCameraId,
                streamUrl: trimmed,
                host: '127.0.0.1',
                port: 554,
                path: '/live/ch0'
            };
        }
        const username = match[1] ? decodeURIComponent(match[1]) : undefined;
        const password = match[2] ? decodeURIComponent(match[2]) : undefined;
        const host = match[3];
        const port = match[4] ? parseInt(match[4], 10) : 554;
        const path = match[5] || '/live/ch0';
        return {
            cameraId: defaultCameraId,
            streamUrl: trimmed,
            username,
            password,
            host,
            port,
            path
        };
    }
    /**
     * 보안용 마스킹된 RTSP URL 반환 (로그 출력용)
     */
    static maskStreamUrl(streamUrl) {
        return streamUrl.replace(/\/\/[^:]+:[^@]+@/, '//***:***@');
    }
}
exports.RtspUrlParser = RtspUrlParser;
/**
 * 지수 백오프 기반 무한 자동 재연결 제어기
 * - 네트워크 단선 또는 카메라 재부팅 시 지수 백오프 적용 (1초 -> 2초 -> 4초 -> ... 최대 30초)
 * - 연결 복구 성공 시 즉시 초기 딜레이로 자동 리셋
 */
class ReconnectBackoffManager {
    initialDelayMs;
    maxDelayMs;
    backoffFactor;
    maxRetries;
    jitter;
    state = {
        attemptCount: 0,
        currentDelayMs: 0,
        lastAttemptTimeMs: 0,
        isConnected: false,
        isReconnecting: false,
        totalReconnectSuccesses: 0
    };
    constructor(options) {
        this.initialDelayMs = options?.initialDelayMs ?? 1000;
        this.maxDelayMs = options?.maxDelayMs ?? 30000;
        this.backoffFactor = Math.max(1.1, options?.backoffFactor ?? 2.0);
        this.maxRetries = options?.maxRetries ?? Infinity;
        this.jitter = options?.jitter ?? true;
        this.state.currentDelayMs = this.initialDelayMs;
    }
    /**
     * 다음 재시도까지 대기해야 할 지연 시간(ms) 계산 및 시도 횟수 증가
     */
    getNextBackoffDelayMs() {
        if (this.state.attemptCount >= this.maxRetries) {
            return { delayMs: 0, canRetry: false, attemptCount: this.state.attemptCount };
        }
        this.state.attemptCount += 1;
        this.state.lastAttemptTimeMs = Date.now();
        this.state.isReconnecting = true;
        this.state.isConnected = false;
        // 지수 증가: initial * (factor ^ (attempt - 1))
        const rawDelay = this.initialDelayMs * Math.pow(this.backoffFactor, this.state.attemptCount - 1);
        let delay = Math.min(this.maxDelayMs, rawDelay);
        if (this.jitter) {
            // 0.85 ~ 1.15 무작위 지터
            const jitterFactor = 0.85 + Math.random() * 0.3;
            delay = Math.round(delay * jitterFactor);
        }
        this.state.currentDelayMs = delay;
        return {
            delayMs: delay,
            canRetry: true,
            attemptCount: this.state.attemptCount
        };
    }
    /**
     * 스트림 연결 성공 시 재연결 상태 및 딜레이 리셋
     */
    onConnectionSuccess() {
        if (this.state.isReconnecting) {
            this.state.totalReconnectSuccesses += 1;
        }
        this.state.isConnected = true;
        this.state.isReconnecting = false;
        this.state.attemptCount = 0;
        this.state.currentDelayMs = this.initialDelayMs;
    }
    /**
     * 연결 단선/에러 발생 시
     */
    onConnectionLost() {
        this.state.isConnected = false;
    }
    getState() {
        return { ...this.state };
    }
    reset() {
        this.state = {
            attemptCount: 0,
            currentDelayMs: this.initialDelayMs,
            lastAttemptTimeMs: 0,
            isConnected: false,
            isReconnecting: false,
            totalReconnectSuccesses: 0
        };
    }
}
exports.ReconnectBackoffManager = ReconnectBackoffManager;
/**
 * RtspStreamBuffer: RTSP 실시간 스트림 링 버퍼 관리자
 * - 메모리 누수 0%: 상한 시간(30~60초) 초과 시 가장 오래된 청크를 FIFO 자동 폐기
 * - tmpfs 연동 시 물리 디스크 I/O 없이 고속 롤링
 * - Tuya/ONVIF 카메라 RTSP 설정 파서 및 재연결 지수 백오프 통합
 */
class RtspStreamBuffer {
    cameraId;
    maxDurationSec;
    maxMemoryBytes;
    tmpfsDir;
    cameraConfig;
    reconnectManager;
    chunks = [];
    totalBytes = 0;
    constructor(options) {
        this.cameraId = options.cameraId;
        this.maxDurationSec = options.maxDurationSec ?? 30;
        this.maxMemoryBytes = options.maxMemoryBytes ?? 500 * 1024 * 1024; // 500MB
        this.tmpfsDir = options.tmpfsDir;
        this.cameraConfig = options.cameraConfig
            ? RtspUrlParser.parse(options.cameraConfig)
            : undefined;
        this.reconnectManager = new ReconnectBackoffManager(options.reconnectPolicy);
    }
    getCameraConfig() {
        return this.cameraConfig;
    }
    getReconnectManager() {
        return this.reconnectManager;
    }
    /**
     * 신규 2초 단위 세그먼트 청크 인입
     */
    pushChunk(chunk) {
        if (chunk.cameraId !== this.cameraId) {
            return;
        }
        // 데이터 인입 시 정상 연결 상태로 마킹
        this.reconnectManager.onConnectionSuccess();
        this.chunks.push(chunk);
        this.totalBytes += chunk.sizeBytes;
        // 롤링 검사: 최대 시간(초) 또는 메모리 상한 초과 시 FIFO 폐기
        this.enforceLimits();
    }
    /**
     * 특정 이벤트 시점 기준 전후 시간 윈도우(예: 전 10초 + 후 5초)에 해당하는 청크 목록 추출
     */
    getSegmentsForWindow(triggerTimeMs, preSec = 10, postSec = 5) {
        const windowStartMs = triggerTimeMs - (preSec * 1000);
        const windowEndMs = triggerTimeMs + (postSec * 1000);
        return this.chunks.filter((chunk) => {
            // 윈도우 구간과 조금이라도 겹치는 세그먼트 모두 선택
            return chunk.endTimeMs >= windowStartMs && chunk.startTimeMs <= windowEndMs;
        });
    }
    /**
     * 상한 초과 청크 FIFO 삭제 및 메모리/임시파일 해제
     */
    enforceLimits() {
        if (this.chunks.length === 0)
            return;
        const latestEndTime = this.chunks[this.chunks.length - 1].endTimeMs;
        const oldestAllowedStartTime = latestEndTime - (this.maxDurationSec * 1000);
        while (this.chunks.length > 0) {
            const oldest = this.chunks[0];
            const isTimeExpired = oldest.endTimeMs < oldestAllowedStartTime;
            const isMemoryOverflow = this.totalBytes > this.maxMemoryBytes;
            if (!isTimeExpired && !isMemoryOverflow) {
                break;
            }
            // FIFO 방출
            const removed = this.chunks.shift();
            if (removed) {
                this.totalBytes = Math.max(0, this.totalBytes - removed.sizeBytes);
                this.cleanupChunkFile(removed.filePath);
            }
        }
    }
    cleanupChunkFile(filePath) {
        if (!filePath)
            return;
        try {
            if (fs_1.default.existsSync(filePath)) {
                fs_1.default.unlinkSync(filePath);
            }
        }
        catch {
            // 안전 무시 (파일 락 등)
        }
    }
    getStats() {
        const totalDurationSec = this.chunks.reduce((acc, c) => acc + c.durationSec, 0);
        return {
            chunkCount: this.chunks.length,
            totalDurationSec,
            totalBytes: this.totalBytes
        };
    }
    getChunks() {
        return this.chunks;
    }
    clear() {
        for (const chunk of this.chunks) {
            this.cleanupChunkFile(chunk.filePath);
        }
        this.chunks = [];
        this.totalBytes = 0;
    }
}
exports.RtspStreamBuffer = RtspStreamBuffer;
