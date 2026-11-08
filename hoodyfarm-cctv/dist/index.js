"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
__exportStar(require("./types/cctv"), exports);
__exportStar(require("./stream/RtspStreamBuffer"), exports);
__exportStar(require("./pipeline/DiskStorageGuard"), exports);
__exportStar(require("./pipeline/ClipGenerator"), exports);
__exportStar(require("./pipeline/CloudUploader"), exports);
__exportStar(require("./pipeline/InferenceEngine"), exports);
__exportStar(require("./webhook/FmsEmergencyDispatcher"), exports);
__exportStar(require("./visionEventDispatcher"), exports);
__exportStar(require("./health/CctvHealthServer"), exports);
const RtspStreamBuffer_1 = require("./stream/RtspStreamBuffer");
const CctvHealthServer_1 = require("./health/CctvHealthServer");
const DiskStorageGuard_1 = require("./pipeline/DiskStorageGuard");
console.log('📹 [Hoodyfarm CCTV] 온프레미스 AI 비전 숏클립 & 1초 긴급 웹훅 파이프라인 모듈 로드 완료');
// 독립 프로세스 직접 실행 시(PM2 또는 node dist/index.js) 데몬 서버 자동 시작
if (require.main === module) {
    const defaultCameraId = process.env.DEFAULT_CAMERA_ID || 'CAM_BARN_01';
    const streamUrl = process.env.RTSP_STREAM_URL || 'rtsp://admin:hoodyfarm123@192.168.1.101:554/live/ch0';
    const rtspBuffer = new RtspStreamBuffer_1.RtspStreamBuffer({
        cameraId: defaultCameraId,
        maxDurationSec: 30,
        cameraConfig: {
            cameraId: defaultCameraId,
            streamUrl
        }
    });
    // 온프레미스 노드 초기화 알림
    rtspBuffer.getReconnectManager().onConnectionSuccess();
    const diskGuard = new DiskStorageGuard_1.DiskStorageGuard({ minFreeSpaceMb: 500 });
    const healthServer = new CctvHealthServer_1.CctvHealthServer({
        rtspBuffer,
        diskGuard
    });
    healthServer.start().then((port) => {
        console.log(`🚀 [Hoodyfarm CCTV] 24/7 무인 자동복구 백그라운드 데몬 가동 중 (Health Port: ${port})`);
    }).catch((err) => {
        console.error('❌ [Hoodyfarm CCTV] 데몬 기동 오류:', err);
        process.exit(1);
    });
    // 안전 종료(Graceful Shutdown) 처리
    const shutdown = async () => {
        console.log('\n🛑 [Hoodyfarm CCTV] 프로세스 안전 종료 시작 (Graceful Shutdown)...');
        try {
            await healthServer.stop();
            rtspBuffer.clear();
            console.log('✅ [Hoodyfarm CCTV] 데몬 및 링버퍼 안전 정리 완료.');
        }
        finally {
            process.exit(0);
        }
    };
    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
}
