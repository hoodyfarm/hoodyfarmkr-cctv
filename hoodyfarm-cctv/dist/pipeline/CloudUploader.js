"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.CloudUploader = void 0;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
/**
 * CloudUploader: 생성된 MP4 숏클립을 Google Drive / S3 / CDN 스토리지로 비동기 업로드
 * - FMS 긴급 웹훅에 전달할 공개/다운로드 URL 발급
 * - 네트워크 일시 오류 지수 백오프 재시도 (최대 3회)
 * - 로컬 모의 업로드 및 현장 테스트 완비
 */
class CloudUploader {
    storageType;
    bucketOrFolderId;
    cdnPrefix;
    maxRetries;
    timeoutMs;
    simulateLatencyMs;
    customUploadFn;
    constructor(options, customUploadFn) {
        this.storageType = options?.storageType || process.env.STORAGE_TYPE || 'LOCAL_MOCK';
        this.bucketOrFolderId = options?.bucketOrFolderId || process.env.CLOUD_STORAGE_BUCKET || 'hoodyfarm-cctv-clips';
        this.cdnPrefix = options?.cdnPrefix || process.env.CDN_PREFIX || 'https://storage.hoodyfarm.com/clips';
        this.maxRetries = options?.maxRetries ?? 3;
        this.timeoutMs = options?.timeoutMs ?? 5000;
        this.simulateLatencyMs = options?.simulateLatencyMs ?? 0;
        this.customUploadFn = customUploadFn;
    }
    /**
     * 커스텀 업로더 함수 주입
     */
    setUploadFn(fn) {
        this.customUploadFn = fn;
    }
    /**
     * 로컬 MP4 파일을 클라우드로 비동기 업로드
     * @param localFilePath 로컬 MP4 파일 경로
     * @param remoteFileName 클라우드 저장 파일명 (미지정 시 basename 사용)
     */
    async uploadClip(localFilePath, remoteFileName) {
        const fileName = remoteFileName || path_1.default.basename(localFilePath);
        const nowIso = new Date().toISOString();
        // 1. 로컬 파일 존재 검사
        if (!fs_1.default.existsSync(localFilePath)) {
            return {
                success: false,
                fileKey: fileName,
                downloadUrl: '',
                bytesUploaded: 0,
                storageType: this.storageType,
                uploadedAt: nowIso,
                error: `업로드 대상 로컬 파일이 존재하지 않습니다: ${localFilePath}`
            };
        }
        let fileSize = 0;
        try {
            const stat = fs_1.default.statSync(localFilePath);
            fileSize = stat.size;
        }
        catch (err) {
            return {
                success: false,
                fileKey: fileName,
                downloadUrl: '',
                bytesUploaded: 0,
                storageType: this.storageType,
                uploadedAt: nowIso,
                error: `파일 정보 조회 실패: ${err?.message || String(err)}`
            };
        }
        // 2. 모의 지연 시뮬레이션
        if (this.simulateLatencyMs > 0) {
            await new Promise((resolve) => setTimeout(resolve, this.simulateLatencyMs));
        }
        // 3. 커스텀 업로더 또는 스토리지별 전송 로직 실행
        let attempt = 0;
        let lastError = '';
        while (attempt < this.maxRetries) {
            attempt++;
            try {
                if (this.customUploadFn) {
                    const endpoint = `${this.cdnPrefix}/${this.bucketOrFolderId}/${fileName}`;
                    const res = await this.customUploadFn(endpoint, {
                        method: 'PUT',
                        filePath: localFilePath,
                        fileSize,
                        attempt
                    });
                    if (!res.ok) {
                        throw new Error(`HTTP ${res.status} 업로드 거부`);
                    }
                }
                // 성공 URL 생성
                const { downloadUrl, publicViewUrl } = this.generateUrls(fileName);
                return {
                    success: true,
                    fileKey: fileName,
                    downloadUrl,
                    publicViewUrl,
                    bytesUploaded: fileSize,
                    storageType: this.storageType,
                    uploadedAt: new Date().toISOString()
                };
            }
            catch (err) {
                lastError = err?.message || String(err);
                if (attempt < this.maxRetries) {
                    // 지수 백오프 대기 (50ms * attempt)
                    await new Promise((r) => setTimeout(r, 50 * attempt));
                }
            }
        }
        return {
            success: false,
            fileKey: fileName,
            downloadUrl: '',
            bytesUploaded: 0,
            storageType: this.storageType,
            uploadedAt: new Date().toISOString(),
            error: `클라우드 업로드 재시도(${this.maxRetries}회) 실패: ${lastError}`
        };
    }
    /**
     * 스토리지 타입에 따른 다운로드/공개 URL 생성
     */
    generateUrls(fileName) {
        const cleanPrefix = this.cdnPrefix.replace(/\/+$/, '');
        if (this.storageType === 'GDRIVE') {
            const downloadUrl = `https://drive.google.com/uc?export=download&id=${encodeURIComponent(fileName)}`;
            const publicViewUrl = `https://drive.google.com/file/d/${encodeURIComponent(fileName)}/view`;
            return { downloadUrl, publicViewUrl };
        }
        if (this.storageType === 'S3') {
            const downloadUrl = `${cleanPrefix}/${this.bucketOrFolderId}/${encodeURIComponent(fileName)}`;
            const publicViewUrl = `${cleanPrefix}/${this.bucketOrFolderId}/${encodeURIComponent(fileName)}?view=1`;
            return { downloadUrl, publicViewUrl };
        }
        // LOCAL_MOCK
        const downloadUrl = `${cleanPrefix}/${encodeURIComponent(fileName)}`;
        const publicViewUrl = `${cleanPrefix}/view/${encodeURIComponent(fileName)}`;
        return { downloadUrl, publicViewUrl };
    }
}
exports.CloudUploader = CloudUploader;
