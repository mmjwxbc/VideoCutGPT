import axios from 'axios';
import { AnalysisMode, CaptionAssistantSession } from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 60000 * 10,
});

export const captionSessionEventsUrl = (sessionId: string) =>
  `/api/caption/assistant/session/${sessionId}/events`;

export const captionSessionExportedVideoUrl = (sessionId: string) =>
  `/api/caption/assistant/session/${sessionId}/exported-video`;

export interface UploadInitResponse {
  upload_id: string;
  chunk_size: number;
  total_chunks: number;
  uploaded_chunks: number[];
}

export interface UploadStatusResponse {
  upload_id: string;
  total_chunks: number;
  uploaded_chunks: number[];
  complete: boolean;
}

export interface UploadCompleteResponse {
  upload_id: string;
  file_path: string;
  task_id: string;
  status: 'pending' | 'running' | 'done' | 'failed';
}

export interface UploadTaskResponse {
  task_id: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  progress: number;
  result: {
    upload_id: string;
    file_path: string;
    probe?: unknown;
  } | null;
  error: string | null;
}

export interface ChunkUploadResult {
  uploadId: string;
  filePath: string;
  taskId: string;
}

export interface B2UploadUrlResponse {
  upload_url: string;
  authorization_token: string;
  file_name: string;
  content_type: string;
}

export interface B2UploadResult {
  fileId: string;
  fileName: string;
}

const DEFAULT_CHUNK_SIZE = 512 * 1024;
const UPLOAD_STATE_PREFIX = 'caption-upload:';
const ALLOWED_VIDEO_TYPES = new Set([
  'video/mp4',
  'video/quicktime',
  'video/webm',
  'video/x-matroska',
]);

const buildUploadStorageKey = (file: File) =>
  `${UPLOAD_STATE_PREFIX}${file.name}:${file.size}:${file.lastModified}:${file.type}`;

const readStoredUploadId = (file: File) => {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage.getItem(buildUploadStorageKey(file));
};

const writeStoredUploadId = (file: File, uploadId: string) => {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(buildUploadStorageKey(file), uploadId);
};

const clearStoredUploadId = (file: File) => {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.removeItem(buildUploadStorageKey(file));
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

const toHex = (buffer: ArrayBuffer) =>
  Array.from(new Uint8Array(buffer))
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');

const sha1File = async (file: File) => {
  const arrayBuffer = await file.arrayBuffer();
  const digest = await window.crypto.subtle.digest('SHA-1', arrayBuffer);
  return toHex(digest);
};

const initChunkUpload = async (
  file: File,
  chunkSize: number,
): Promise<UploadInitResponse> => {
  const totalChunks = Math.ceil(file.size / chunkSize);
  const response = await api.post('/caption/uploads/init', {
    filename: file.name,
    file_size: file.size,
    chunk_size: chunkSize,
    total_chunks: totalChunks,
    content_type: file.type,
  });
  return response.data;
};

export const getUploadStatus = async (uploadId: string): Promise<UploadStatusResponse> => {
  const response = await api.get(`/caption/uploads/${uploadId}/status`);
  return response.data;
};

export const completeChunkUpload = async (
  uploadId: string,
): Promise<UploadCompleteResponse> => {
  const response = await api.post(`/caption/uploads/${uploadId}/complete`);
  return response.data;
};

export const getUploadTask = async (taskId: string): Promise<UploadTaskResponse> => {
  const response = await api.get(`/caption/tasks/${taskId}`);
  return response.data;
};

export const waitForUploadTask = async (
  taskId: string,
  onProgress?: (task: UploadTaskResponse) => void,
): Promise<UploadTaskResponse> => {
  while (true) {
    const task = await getUploadTask(taskId);
    onProgress?.(task);
    if (task.status === 'done') {
      return task;
    }
    if (task.status === 'failed') {
      throw new Error(task.error || '视频后台处理失败');
    }
    await sleep(1500);
  }
};

export const uploadChunkWithRetry = async (
  uploadId: string,
  formData: FormData,
  maxRetries: number,
) => {
  let lastError: unknown;

  for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
    try {
      return await api.post(`/caption/uploads/${uploadId}/chunk`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60000,
      });
    } catch (error) {
      lastError = error;
      if (attempt === maxRetries) {
        break;
      }
      await sleep(attempt * 1000);
    }
  }

  throw lastError;
};

export const uploadVideoInChunks = async (
  file: File,
  options?: {
    chunkSize?: number;
    onUploadProgress?: (progress: number, uploadedChunks: number, totalChunks: number) => void;
    onTaskProgress?: (task: UploadTaskResponse) => void;
  },
): Promise<ChunkUploadResult> => {
  if (!ALLOWED_VIDEO_TYPES.has(file.type)) {
    throw new Error('仅支持 mp4/mov/webm/mkv 视频类型');
  }

  const chunkSize = options?.chunkSize ?? DEFAULT_CHUNK_SIZE;
  const totalChunks = Math.ceil(file.size / chunkSize);
  const storedUploadId = readStoredUploadId(file);

  let initResp: UploadInitResponse | null = null;
  if (storedUploadId) {
    try {
      const status = await getUploadStatus(storedUploadId);
      if (status.complete) {
        const completeResp = await completeChunkUpload(storedUploadId);
        const task = await waitForUploadTask(completeResp.task_id, options?.onTaskProgress);
        clearStoredUploadId(file);
        return {
          uploadId: storedUploadId,
          filePath: completeResp.file_path || task.result?.file_path || '',
          taskId: completeResp.task_id,
        };
      }
      if (status.total_chunks === totalChunks) {
        initResp = {
          upload_id: storedUploadId,
          chunk_size: chunkSize,
          total_chunks: totalChunks,
          uploaded_chunks: status.uploaded_chunks,
        };
      }
    } catch {
      clearStoredUploadId(file);
    }
  }

  if (!initResp) {
    initResp = await initChunkUpload(file, chunkSize);
    writeStoredUploadId(file, initResp.upload_id);
  }

  const uploadId = initResp.upload_id;
  const uploadedChunks = new Set(initResp.uploaded_chunks || []);
  options?.onUploadProgress?.(uploadedChunks.size / totalChunks, uploadedChunks.size, totalChunks);

  for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
    if (uploadedChunks.has(chunkIndex)) {
      continue;
    }

    const start = chunkIndex * chunkSize;
    const end = Math.min(file.size, start + chunkSize);
    const blob = file.slice(start, end);
    const formData = new FormData();
    formData.append('chunk_index', String(chunkIndex));
    formData.append('chunk', blob, `${file.name}.part${chunkIndex}`);

    await uploadChunkWithRetry(uploadId, formData, 3);
    uploadedChunks.add(chunkIndex);
    options?.onUploadProgress?.(
      uploadedChunks.size / totalChunks,
      uploadedChunks.size,
      totalChunks,
    );
  }

  const completeResp = await completeChunkUpload(uploadId);
  const task = await waitForUploadTask(completeResp.task_id, options?.onTaskProgress);
  clearStoredUploadId(file);

  return {
    uploadId,
    filePath: completeResp.file_path || task.result?.file_path || '',
    taskId: completeResp.task_id,
  };
};

export const getB2UploadUrl = async (file: File): Promise<B2UploadUrlResponse> => {
  const response = await api.post('/caption/storage/b2/upload-url', {
    filename: file.name,
    content_type: file.type,
    file_size: file.size,
  });
  return response.data;
};

export const uploadVideoToB2 = async (
  file: File,
  options?: {
    onUploadProgress?: (progress: number) => void;
  },
): Promise<B2UploadResult> => {
  if (!ALLOWED_VIDEO_TYPES.has(file.type)) {
    throw new Error('仅支持 mp4/mov/webm/mkv 视频类型');
  }

  const uploadTarget = await getB2UploadUrl(file);
  const sha1 = await sha1File(file);
  const response = await axios.post(uploadTarget.upload_url, file, {
    headers: {
      Authorization: uploadTarget.authorization_token,
      'X-Bz-File-Name': encodeURIComponent(uploadTarget.file_name),
      'Content-Type': uploadTarget.content_type,
      'X-Bz-Content-Sha1': sha1,
    },
    timeout: 60000 * 10,
    onUploadProgress: (event) => {
      const total = event.total ?? file.size;
      const loaded = event.loaded ?? 0;
      const progress = total > 0 ? Math.min(1, loaded / total) : 0;
      options?.onUploadProgress?.(progress);
    },
  });

  const fileId = response.data?.fileId;
  const fileName = response.data?.fileName;
  if (typeof fileId !== 'string' || !fileId) {
    throw new Error('B2 上传成功，但没有返回 fileId');
  }

  return {
    fileId,
    fileName: typeof fileName === 'string' && fileName ? fileName : uploadTarget.file_name,
  };
};

export const createCaptionAssistantSession = async (
  payload: {
    uploadedFilePaths?: string[];
    uploadedFileIds?: string[];
  },
  platform: string,
  prompt: string,
  productManual: string | null,
  analysisMode: AnalysisMode,
): Promise<CaptionAssistantSession> => {
  const response = await api.post('/caption/assistant/session', {
    uploaded_file_paths: payload.uploadedFilePaths ?? [],
    uploaded_file_ids: payload.uploadedFileIds ?? [],
    platform,
    prompt,
    analysis_mode: analysisMode,
    product_manual: productManual,
  });
  return response.data;
};

export const continueCaptionAssistantSession = async (
  sessionId: string,
  prompt: string,
): Promise<CaptionAssistantSession> => {
  const response = await api.post(
    `/caption/assistant/session/${sessionId}/message`,
    { prompt },
  );

  return response.data;
};

export const getCaptionAssistantSession = async (
  sessionId: string,
): Promise<CaptionAssistantSession> => {
  const response = await api.get(`/caption/assistant/session/${sessionId}`);
  return response.data;
};

export const listCaptionAssistantSessions = async (): Promise<CaptionAssistantSession[]> => {
  const response = await api.get('/caption/assistant/sessions');
  return response.data;
};

export default api;
