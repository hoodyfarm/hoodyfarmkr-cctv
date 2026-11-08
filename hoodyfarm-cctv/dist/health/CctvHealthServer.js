"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.CctvHealthServer = void 0;
const http_1 = __importDefault(require("http"));
const DiskStorageGuard_1 = require("../pipeline/DiskStorageGuard");
class CctvHealthServer {
    server = null;
    port;
    nodeId;
    startTime;
    rtspBuffer;
    diskGuard;
    constructor(options) {
        this.port = options.port ?? (Number(process.env.AI_SERVER_PORT || process.env.PORT) || 8080);
        this.nodeId = options.nodeId ?? (process.env.AI_NODE_ID || 'HOODY_CCTV_NODE_01');
        this.rtspBuffer = options.rtspBuffer;
        this.diskGuard = options.diskGuard ?? new DiskStorageGuard_1.DiskStorageGuard({ minFreeSpaceMb: 500 });
        this.startTime = Date.now();
    }
    /**
     * 헬스체크 응답 DTO 객체 생성
     */
    getHealthData() {
        const reconnectState = this.rtspBuffer.getReconnectManager().getState();
        const stats = this.rtspBuffer.getStats();
        const diskUsage = this.diskGuard.getDiskUsage('.');
        const safeCheck = this.diskGuard.isSafeToStore('.');
        const mem = process.memoryUsage();
        const isConnected = reconnectState.isConnected;
        const isSafe = safeCheck.isSafe;
        let status = 'UP';
        if (!isConnected || !isSafe) {
            status = 'DEGRADED';
        }
        return {
            status,
            timestamp: new Date().toISOString(),
            uptimeSec: Math.floor((Date.now() - this.startTime) / 1000),
            nodeId: this.nodeId,
            rtsp: {
                isConnected,
                reconnectAttempts: reconnectState.attemptCount,
                totalReconnectSuccesses: reconnectState.totalReconnectSuccesses,
                ringBufferSeconds: stats.totalDurationSec,
                ringBufferChunks: stats.chunkCount,
                ringBufferBytes: stats.totalBytes
            },
            storage: {
                diskFreeMb: diskUsage.freeMb,
                diskTotalMb: diskUsage.totalMb,
                diskUsagePercent: Number(diskUsage.usagePercent.toFixed(1)),
                isSafeToStore: isSafe
            },
            memory: {
                rssMb: Math.round(mem.rss / (1024 * 1024)),
                heapUsedMb: Math.round(mem.heapUsed / (1024 * 1024)),
                heapTotalMb: Math.round(mem.heapTotal / (1024 * 1024))
            }
        };
    }
    /**
     * HTTP 헬스체크 서버 기동
     */
    start() {
        return new Promise((resolve, reject) => {
            this.server = http_1.default.createServer((req, res) => {
                const url = req.url || '/';
                if (url === '/health' || url === '/') {
                    const healthData = this.getHealthData();
                    const statusCode = healthData.status === 'DOWN' ? 503 : 200;
                    res.writeHead(statusCode, {
                        'Content-Type': 'application/json; charset=utf-8',
                        'Cache-Control': 'no-cache, no-store, must-revalidate'
                    });
                    res.end(JSON.stringify(healthData, null, 2));
                    return;
                }
                if (url === '/live') {
                    // Liveness probe (프로세스 생존 여부만 200 반환)
                    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
                    res.end('OK');
                    return;
                }
                res.writeHead(404, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Not Found', path: url }));
            });
            this.server.on('error', (err) => {
                reject(err);
            });
            this.server.listen(this.port, () => {
                console.log(`📡 [CctvHealthServer] 헬스체크 서버 기동 완료: http://0.0.0.0:${this.port}/health (Node: ${this.nodeId})`);
                resolve(this.port);
            });
        });
    }
    /**
     * 서버 정지
     */
    stop() {
        return new Promise((resolve) => {
            if (this.server) {
                this.server.close(() => {
                    this.server = null;
                    resolve();
                });
            }
            else {
                resolve();
            }
        });
    }
    getPort() {
        return this.port;
    }
}
exports.CctvHealthServer = CctvHealthServer;
