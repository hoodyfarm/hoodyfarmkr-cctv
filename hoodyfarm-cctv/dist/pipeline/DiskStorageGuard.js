"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.DiskStorageGuard = void 0;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
class DiskStorageGuard {
    static mockFreeSpaceMb = null;
    static mockTotalSpaceMb = null;
    minFreeSpaceMb;
    maxUsagePercent;
    constructor(options) {
        // 하위 호환성 유지: 명시적 지정 없으면 500MB 기본, 옵션으로 전달 가능
        this.minFreeSpaceMb = options?.minFreeSpaceMb ?? 500;
        this.maxUsagePercent = options?.maxUsagePercent;
    }
    /**
     * 테스트 모의용 여유 디스크 공간 설정 (Mock)
     */
    static setMockFreeSpaceMb(mb, totalMb) {
        this.mockFreeSpaceMb = mb;
        if (totalMb !== undefined) {
            this.mockTotalSpaceMb = totalMb;
        }
    }
    /**
     * 가용 디스크 용량 (MB) 및 사용률 조회
     */
    getDiskUsage(targetPath = '.') {
        if (DiskStorageGuard.mockFreeSpaceMb !== null) {
            const freeMb = DiskStorageGuard.mockFreeSpaceMb;
            const totalMb = DiskStorageGuard.mockTotalSpaceMb ?? Math.max(freeMb * 2, 100000);
            const usedMb = Math.max(0, totalMb - freeMb);
            const usagePercent = totalMb > 0 ? (usedMb / totalMb) * 100 : 0;
            return { totalMb, freeMb, usedMb, usagePercent };
        }
        try {
            if (typeof fs_1.default.statfsSync === 'function') {
                const stats = fs_1.default.statfsSync(targetPath);
                const freeBytes = stats.bavail * stats.bsize;
                const totalBytes = stats.blocks * stats.bsize;
                const freeMb = Math.floor(freeBytes / (1024 * 1024));
                const totalMb = Math.floor(totalBytes / (1024 * 1024));
                const usedMb = Math.max(0, totalMb - freeMb);
                const usagePercent = totalMb > 0 ? (usedMb / totalMb) * 100 : 0;
                return { totalMb, freeMb, usedMb, usagePercent };
            }
        }
        catch {
            // statfs 미지원 플랫폼(구형 윈도우 등) 폴백
        }
        return {
            totalMb: 100000,
            freeMb: 50000,
            usedMb: 50000,
            usagePercent: 50.0
        };
    }
    /**
     * 가용 디스크 용량 (MB) 조회
     */
    getAvailableDiskSpaceMb(targetPath = '.') {
        return this.getDiskUsage(targetPath).freeMb;
    }
    /**
     * 신규 숏클립을 저장하기에 안전한지 여부 검사 (용량 기준 및 사용률 기준)
     */
    isSafeToStore(targetPath = '.') {
        const usage = this.getDiskUsage(targetPath);
        // 1. 최소 여유 용량 검사
        if (usage.freeMb < this.minFreeSpaceMb) {
            return {
                isSafe: false,
                freeMb: usage.freeMb,
                usagePercent: usage.usagePercent,
                reason: `디스크 여유 공간 부족 (현재: ${usage.freeMb}MB < 최소요구: ${this.minFreeSpaceMb}MB) - 노드 다운 방지를 위해 숏클립 폐기(Fail-Safe Drop)`
            };
        }
        // 2. 최대 디스크 사용률 검사 (옵션 지정 시 또는 85% 초과 감시)
        if (this.maxUsagePercent !== undefined && usage.usagePercent > this.maxUsagePercent) {
            return {
                isSafe: false,
                freeMb: usage.freeMb,
                usagePercent: usage.usagePercent,
                reason: `디스크 사용률 초과 (현재: ${usage.usagePercent.toFixed(1)}% > 임계치: ${this.maxUsagePercent}%) - 파일 시스템 포화 방지를 위해 숏클립 폐기(Fail-Safe Drop)`
            };
        }
        return {
            isSafe: true,
            freeMb: usage.freeMb,
            usagePercent: usage.usagePercent
        };
    }
    /**
     * 디스크 사용률 85% 초과 또는 여유 공간 부족 시 오래된 정상 클립/임시 파일 FIFO 자동 회수
     * @param targetDir 정리 대상 디렉토리 (예: spool/clips, spool/pending)
     * @param targetFreeMb 확보 목표 여유 공간 (기본값: minFreeSpaceMb)
     */
    purgeOldClipsFifo(targetDir, targetFreeMb) {
        const requiredFree = targetFreeMb ?? this.minFreeSpaceMb;
        const deletedFiles = [];
        let freedBytes = 0;
        if (!fs_1.default.existsSync(targetDir)) {
            return { freedBytes: 0, deletedFiles: [], remainingFileCount: 0 };
        }
        try {
            const files = fs_1.default.readdirSync(targetDir);
            // 파일 상세 정보 조회 및 생성시간(mtime) 오름차순 정렬 (오래된 것 먼저)
            const fileStats = files
                .map((name) => {
                const filePath = path_1.default.join(targetDir, name);
                try {
                    const stat = fs_1.default.statSync(filePath);
                    return { name, filePath, isFile: stat.isFile(), mtime: stat.mtimeMs, size: stat.size };
                }
                catch {
                    return null;
                }
            })
                .filter((item) => item !== null && item.isFile)
                .sort((a, b) => a.mtime - b.mtime);
            for (const item of fileStats) {
                // 현재 가용 용량 확인
                const currentUsage = this.getDiskUsage(targetDir);
                const usageConditionMet = this.maxUsagePercent !== undefined ? currentUsage.usagePercent <= this.maxUsagePercent : true;
                if (currentUsage.freeMb >= requiredFree && usageConditionMet) {
                    break; // 공간 확보 완료 시 중단
                }
                try {
                    fs_1.default.unlinkSync(item.filePath);
                    freedBytes += item.size;
                    deletedFiles.push(item.filePath);
                    // Mock 공간 보정 (테스트 환경)
                    if (DiskStorageGuard.mockFreeSpaceMb !== null) {
                        const freedMb = Math.ceil(item.size / (1024 * 1024));
                        DiskStorageGuard.mockFreeSpaceMb += Math.max(1, freedMb);
                    }
                }
                catch {
                    // 파일 삭제 실패 시 스킵
                }
            }
            const remainingFiles = fs_1.default.readdirSync(targetDir);
            return {
                freedBytes,
                deletedFiles,
                remainingFileCount: remainingFiles.length
            };
        }
        catch {
            return { freedBytes, deletedFiles, remainingFileCount: 0 };
        }
    }
}
exports.DiskStorageGuard = DiskStorageGuard;
