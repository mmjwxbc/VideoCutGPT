import React, { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';

import ConversationPanel from '../components/caption-studio/ConversationPanel';
import HistorySidebar from '../components/caption-studio/HistorySidebar';
import WorkspaceSidebar from '../components/caption-studio/WorkspaceSidebar';
import { DrawerType } from '../components/caption-studio/MobileDrawerTabs';
import {
  CAPTION_UPLOAD_STORAGE_PREFIX,
  captionSessionEventsUrl,
  continueCaptionAssistantSession,
  createCaptionAssistantSession,
  getCaptionAssistantAccessIdentity,
  getCaptionAssistantSession,
  isLikelyAccessAuthError,
  listCaptionAssistantSessions,
  uploadVideoToB2,
  uploadVideoInChunks,
} from '../api/api';
import { SessionListItem, buildSessionHistoryItem, buildSessionHistoryItemFromSummary, getWorkflowRows } from '../components/caption-studio/shared';
import { AnalysisMode, CaptionAssistantSession, CaptionAssistantSessionSummary, TurnEventItem } from '../types';

const PLATFORM_OPTIONS = [
  { value: 'tiktok', label: 'TikTok', iconClassName: 'bg-slate-900' },
  { value: 'douyin', label: 'Douyin', iconClassName: 'bg-rose-500' },
  { value: 'youtube', label: 'YouTube', iconClassName: 'bg-red-500' },
  { value: 'instagram', label: 'Instagram', iconClassName: 'bg-fuchsia-500' },
];

const SSE_INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000;
const ACTIVE_SESSION_STORAGE_KEY = 'caption-active-session-id';
const ACCESS_RECOVERY_MESSAGE = '检测到登录状态异常，无法访问会话接口。请重新认证后重试。';
const ACCESS_REAUTH_PATH = '/api/access/complete';

type UploadPreviewStatus = 'idle' | 'uploading' | 'processing' | 'done' | 'failed';

interface UploadPreviewState {
  progress: number;
  status: UploadPreviewStatus;
}

const isStaleSessionVersion = (nextVersion?: number, currentVersion?: number) => {
  if (typeof nextVersion !== 'number' || typeof currentVersion !== 'number') {
    return false;
  }
  return nextVersion < currentVersion;
};

const getAxiosErrorMessage = (error: unknown, fallback: string) => {
  if (!axios.isAxiosError(error)) {
    return fallback;
  }
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === 'object') {
    if ('error' in detail && Array.isArray(detail.missing_chunks)) {
      return `分片缺失：${detail.missing_chunks.join(', ')}`;
    }
    return JSON.stringify(detail);
  }
  return error.message || fallback;
};

const isValidCaptionSessionSummary = (value: unknown): value is CaptionAssistantSessionSummary => {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as Partial<CaptionAssistantSessionSummary>;
  return (
    typeof candidate.session_id === 'string' &&
    typeof candidate.platform === 'string' &&
    typeof candidate.analysis_mode === 'string' &&
    typeof candidate.status === 'string' &&
    typeof candidate.title === 'string' &&
    typeof candidate.subtitle === 'string'
  );
};

const isLoopbackHostname = (hostname: string) =>
  hostname === 'localhost' ||
  hostname === '::1' ||
  hostname === '[::1]' ||
  hostname === '127.0.0.1' ||
  hostname.startsWith('127.');

const CaptionGenerator: React.FC = () => {
  const [videos, setVideos] = useState<File[]>([]);
  const [videoPreviewUrls, setVideoPreviewUrls] = useState<string[]>([]);
  const [platform, setPlatform] = useState<string>('tiktok');
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('keyframe');
  const [productManual, setProductManual] = useState<string>('');
  const [sellingPointsOpen, setSellingPointsOpen] = useState<boolean>(false);
  const [draftPrompt, setDraftPrompt] = useState<string>(
    '请先生成适合投放的视频剪辑方案，并输出20s镜头级剪辑方案。最后剪辑导出视频',
  );
  const [session, setSession] = useState<CaptionAssistantSession | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [accessRecoveryRequired, setAccessRecoveryRequired] = useState<boolean>(false);
  const [sseTimedOut, setSseTimedOut] = useState<boolean>(false);
  const [sessionHistory, setSessionHistory] = useState<SessionListItem[]>([]);
  const [composerMode, setComposerMode] = useState<'initial' | 'followup'>(
    'initial',
  );
  const [activeDrawer, setActiveDrawer] = useState<DrawerType | null>(null);
  const [historySidebarCollapsed, setHistorySidebarCollapsed] = useState<boolean>(false);
  const [pendingUserPrompt, setPendingUserPrompt] = useState<string | null>(null);
  const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
  const [selectedUploadIndex, setSelectedUploadIndex] = useState<number>(0);
  const [, setStatusMessage] = useState<string>('');
  const [uploadProgress, setUploadProgress] = useState<UploadPreviewState[]>([]);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const sessionRef = useRef<CaptionAssistantSession | null>(null);
  const sessionEffectTokenRef = useRef(0);

  const turns = session?.turns ?? [];
  const workflowRows = useMemo(
    () => getWorkflowRows(session?.global_editing_state?.workflow),
    [session?.global_editing_state?.workflow],
  );
  const isSessionLoading = loadingSessionId !== null;
  const isRunning = session ? session.status === 'processing' : loading;
  const isInitialUploadInFlight =
    composerMode === 'initial' && pendingUserPrompt !== null && session === null;
  const submitDisabled = isRunning || isInitialUploadInFlight || isSessionLoading;
  const isSubmitting = loading || pendingUserPrompt !== null || isSessionLoading;
  const useLegacyLocalUpload = useMemo(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    return isLoopbackHostname(window.location.hostname);
  }, []);
  const isProtectedDeployment = useMemo(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    return !isLoopbackHostname(window.location.hostname);
  }, []);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  const applyAuthoritativeSession = useCallback((nextSession: CaptionAssistantSession) => {
    setPendingUserPrompt(null);
    sessionRef.current = nextSession;
    setAnalysisMode(nextSession.analysis_mode);
    setSession((current) => {
      if (current && isStaleSessionVersion(nextSession.version, current.version)) {
        return current;
      }
      return nextSession;
    });
    setComposerMode('followup');
    setLoading(nextSession.status === 'processing');
    setAccessRecoveryRequired(false);
    setError('');
  }, []);

  const clearClientSessionStorage = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const localStorageKeys: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key) {
        continue;
      }
      if (
        key === ACTIVE_SESSION_STORAGE_KEY ||
        key.startsWith(CAPTION_UPLOAD_STORAGE_PREFIX)
      ) {
        localStorageKeys.push(key);
      }
    }
    localStorageKeys.forEach((key) => window.localStorage.removeItem(key));
    window.sessionStorage.clear();
  }, []);

  const handleAccessRecovery = useCallback(
    async (nextError: unknown, fallbackMessage: string) => {
      if (isProtectedDeployment && isLikelyAccessAuthError(nextError)) {
        try {
          await getCaptionAssistantAccessIdentity();
          setAccessRecoveryRequired(false);
          setError('登录状态已恢复，正在重试访问会话数据。');
          return false;
        } catch {
          setAccessRecoveryRequired(true);
          setError(ACCESS_RECOVERY_MESSAGE);
          return true;
        }
      }
      setAccessRecoveryRequired(false);
      setError(getAxiosErrorMessage(nextError, fallbackMessage));
      return false;
    },
    [isProtectedDeployment],
  );

  const reloadCurrentPage = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }
    window.location.reload();
  }, []);

  const restartAccessLogin = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }
    clearClientSessionStorage();
    window.location.assign(ACCESS_REAUTH_PATH);
  }, [clearClientSessionStorage]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (!session?.session_id) {
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, session.session_id);
  }, [session?.session_id]);

  const reconcileTerminalSession = useCallback(async (sessionId: string) => {
    try {
      const latestSession = await getCaptionAssistantSession(sessionId);
      applyAuthoritativeSession(latestSession);
    } catch (err) {
      await handleAccessRecovery(err, '读取会话状态失败，请刷新后重试');
      console.error('Error reconciling caption session:', err);
    }
  }, [applyAuthoritativeSession, handleAccessRecovery]);

  const upsertSessionHistory = useCallback(
    (nextSession: CaptionAssistantSession, fallbackTitle?: string) => {
      setSessionHistory((current) => {
        const previousItem = current.find(
          (item) => item.session_id === nextSession.session_id,
        );
        const nextItem = buildSessionHistoryItem(
          nextSession,
          fallbackTitle,
          previousItem,
        );
        const remaining = current.filter(
          (item) => item.session_id !== nextSession.session_id,
        );
        return [nextItem, ...remaining].sort(
          (left, right) =>
            new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
        );
      });
    },
    [],
  );

  useEffect(() => {
    if (!session) {
      return;
    }
    upsertSessionHistory(session);
  }, [session, upsertSessionHistory]);

  const openSessionFromHistory = useCallback(async (sessionId: string) => {
    setLoadingSessionId(sessionId);
    setLoading(true);
    setAccessRecoveryRequired(false);
    setError('');
    try {
      const nextSession = await getCaptionAssistantSession(sessionId);
      startTransition(() => {
        setPendingUserPrompt(null);
        setDraftPrompt('');
        setAnalysisMode(nextSession.analysis_mode);
        setSession(nextSession);
        setComposerMode('followup');
        setActiveDrawer(null);
      });
      upsertSessionHistory(nextSession);
    } catch (err) {
      await handleAccessRecovery(err, '读取历史会话失败，请重试');
      console.error('Error getting caption assistant session:', err);
    } finally {
      setLoadingSessionId(null);
      setLoading(false);
    }
  }, [handleAccessRecovery, upsertSessionHistory]);

  useEffect(() => {
    let cancelled = false;

    const applyLoadedSessions = (sessions: CaptionAssistantSessionSummary[]) => {
      if (cancelled || !sessions.length) {
        return;
      }
      const historyItems = sessions.map((item) => buildSessionHistoryItemFromSummary(item));
      setSessionHistory(historyItems);

      if (typeof window === 'undefined') {
        return;
      }
      const preferredSessionId = window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
      if (!preferredSessionId) {
        return;
      }
      const nextSession = sessions.find((item) => item.session_id === preferredSessionId);
      if (!nextSession || cancelled) {
        return;
      }
      void openSessionFromHistory(nextSession.session_id);
    };

    const loadPersistedSessions = async () => {
      try {
        const sessions = (await listCaptionAssistantSessions()).filter(isValidCaptionSessionSummary);
        applyLoadedSessions(sessions);
      } catch (err) {
        if (!cancelled) {
          if (await handleAccessRecovery(err, '读取历史会话列表失败，请刷新重试')) {
            return;
          }
          if (isLikelyAccessAuthError(err)) {
            try {
              const sessions = (await listCaptionAssistantSessions()).filter(isValidCaptionSessionSummary);
              applyLoadedSessions(sessions);
              return;
            } catch (retryError) {
              setError(getAxiosErrorMessage(retryError, '读取历史会话列表失败，请刷新重试'));
              console.error('Retrying caption sessions after access recovery failed:', retryError);
              return;
            }
          }
          console.error('Error listing caption sessions:', err);
        }
      }
    };

    void loadPersistedSessions();
    return () => {
      cancelled = true;
    };
  }, [handleAccessRecovery, openSessionFromHistory]);

  useEffect(() => {
    if (!session?.session_id) {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      return;
    }

    sessionEffectTokenRef.current += 1;
    const effectToken = sessionEffectTokenRef.current;
    eventSourceRef.current?.close();
    const source = new EventSource(captionSessionEventsUrl(session.session_id));
    eventSourceRef.current = source;
    let inactivityTimer: number | undefined;

    const clearInactivityTimer = () => {
      if (inactivityTimer !== undefined) {
        window.clearTimeout(inactivityTimer);
        inactivityTimer = undefined;
      }
    };

    const closeSource = () => {
      clearInactivityTimer();
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
    };

    const resetInactivityTimer = () => {
      clearInactivityTimer();
      inactivityTimer = window.setTimeout(async () => {
        if (eventSourceRef.current !== source) {
          return;
        }
        closeSource();
        setSseTimedOut(true);
        setError('SSE 连接 30 分钟没有新事件，已停止等待并回查后台状态。');
        await reconcileTerminalSession(session.session_id);
      }, SSE_INACTIVITY_TIMEOUT_MS);
    };

    const handleSnapshot = (raw: MessageEvent<string>) => {
      if (sessionEffectTokenRef.current !== effectToken) {
        return;
      }
      resetInactivityTimer();
      setSseTimedOut(false);
      const nextSession = JSON.parse(raw.data) as CaptionAssistantSession;
      applyAuthoritativeSession(nextSession);
    };

    const handleTurnEvent = (raw: MessageEvent<string>) => {
      if (sessionEffectTokenRef.current !== effectToken) {
        return;
      }
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        turn_id: string;
        version: number;
        updated_at: string;
        event: TurnEventItem;
      };
      setSession((current) => {
        if (!current) {
          return current;
        }
        if (isStaleSessionVersion(payload.version, current.version)) {
          return current;
        }
        return {
          ...current,
          version: payload.version,
          updated_at: payload.updated_at,
          turns: current.turns.map((turn) =>
            turn.turn_id === payload.turn_id
              ? { ...turn, events: [...turn.events, payload.event] }
              : turn,
          ),
        };
      });
    };

    const handleTurnTerminal = (raw: MessageEvent<string>) => {
      if (sessionEffectTokenRef.current !== effectToken) {
        return;
      }
      resetInactivityTimer();
      setSseTimedOut(false);
      const nextSession = JSON.parse(raw.data) as CaptionAssistantSession;
      applyAuthoritativeSession(nextSession);
    };

    source.addEventListener('snapshot', handleSnapshot as EventListener);
    source.addEventListener('turn_event', handleTurnEvent as EventListener);
    source.addEventListener('turn_completed', handleTurnTerminal as EventListener);
    source.addEventListener('turn_error', handleTurnTerminal as EventListener);
    source.addEventListener('ping', (() => {
      if (sessionEffectTokenRef.current !== effectToken) {
        return;
      }
      resetInactivityTimer();
      setSseTimedOut(false);
    }) as EventListener);
    source.onerror = async () => {
      if (sessionEffectTokenRef.current !== effectToken) {
        return;
      }
      console.error('Caption SSE connection interrupted.');
      clearInactivityTimer();
      await reconcileTerminalSession(session.session_id);
      if (eventSourceRef.current === source) {
        resetInactivityTimer();
      }
    };
    resetInactivityTimer();

    return () => {
      closeSource();
    };
  }, [applyAuthoritativeSession, reconcileTerminalSession, session?.session_id]);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) {
      return;
    }
    thread.scrollTop = thread.scrollHeight;
  }, [pendingUserPrompt, turns.length, session?.updated_at]);

  useEffect(() => {
    if (!videos.length) {
      setVideoPreviewUrls([]);
      return;
    }

    const objectUrls = videos.map((video) => URL.createObjectURL(video));
    setVideoPreviewUrls(objectUrls);

    return () => {
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [videos]);

  const handleVideoChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFiles = Array.from(event.target.files ?? []);
    setVideos(nextFiles);
    setUploadProgress(
      nextFiles.map(() => ({
        progress: 0,
        status: 'idle',
      })),
    );
    setSelectedUploadIndex(0);
    event.target.value = '';
  };

  const resetSession = () => {
    sessionEffectTokenRef.current += 1;
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    sessionRef.current = null;
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    }
    setPendingUserPrompt(null);
    setLoadingSessionId(null);
    setSession(null);
    setVideos([]);
    setVideoPreviewUrls([]);
    setUploadProgress([]);
    setSelectedUploadIndex(0);
    setProductManual('');
    setAnalysisMode('keyframe');
    setSellingPointsOpen(false);
    setDraftPrompt('请先生成适合投放的视频剪辑方案，并输出20s镜头级剪辑方案。最后剪辑导出视频');
    setComposerMode('initial');
    setActiveDrawer(null);
    setLoading(false);
    setSseTimedOut(false);
    setAccessRecoveryRequired(false);
    setError('');
    setStatusMessage('');
  };

  const clearUploadedVideo = useCallback(() => {
    setVideos([]);
    setVideoPreviewUrls([]);
    setUploadProgress([]);
    setSelectedUploadIndex(0);
    setStatusMessage('');
  }, []);

  const moveUpload = useCallback((fromIndex: number, toIndex: number) => {
    setVideos((current) => {
      if (
        fromIndex < 0 ||
        toIndex < 0 ||
        fromIndex >= current.length ||
        toIndex >= current.length ||
        fromIndex === toIndex
      ) {
        return current;
      }
      const next = [...current];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
    setUploadProgress((current) => {
      if (
        fromIndex < 0 ||
        toIndex < 0 ||
        fromIndex >= current.length ||
        toIndex >= current.length ||
        fromIndex === toIndex
      ) {
        return current;
      }
      const next = [...current];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
    setSelectedUploadIndex((current) => {
      if (current === fromIndex) {
        return toIndex;
      }
      if (fromIndex < current && toIndex >= current) {
        return current - 1;
      }
      if (fromIndex > current && toIndex <= current) {
        return current + 1;
      }
      return current;
    });
  }, []);

  const submitPrompt = async (promptValue: string) => {
    const normalizedPrompt = promptValue.trim();

    if (composerMode === 'initial') {
      if (!videos.length) {
        setError('请先上传至少一个视频文件');
        return;
      }

      if (!normalizedPrompt) {
        setError('请输入你的首轮创作要求');
        return;
      }

      setLoading(true);
      setSseTimedOut(false);
      setAccessRecoveryRequired(false);
      setError('');
      setStatusMessage(
        useLegacyLocalUpload ? '准备分片上传视频...' : '准备直传视频到 B2...',
      );
      setPendingUserPrompt(normalizedPrompt);
      setUploadProgress((current) =>
        current.map((item) => ({
          ...item,
          progress: 0,
          status: 'uploading',
        })),
      );

      try {
        const uploadedFilePaths: string[] = [];
        const uploadedFileIds: string[] = [];
        for (let index = 0; index < videos.length; index += 1) {
          const currentFile = videos[index];
          const fileLabel =
            videos.length === 1
              ? currentFile.name
              : `${index + 1}/${videos.length} ${currentFile.name}`;
          if (useLegacyLocalUpload) {
            const uploadResult = await uploadVideoInChunks(currentFile, {
              onUploadProgress: (progress, uploadedChunks, totalChunks) => {
                setUploadProgress((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index
                      ? {
                        progress,
                        status: progress >= 1 ? 'processing' : 'uploading',
                      }
                      : item,
                  ),
                );
                setStatusMessage(
                  `上传视频 ${fileLabel}：已完成 ${uploadedChunks}/${totalChunks} 分片（${Math.round(
                    progress * 100,
                  )}%）`,
                );
              },
              onTaskProgress: (task) => {
                const percent = Math.round(task.progress * 100);
                setUploadProgress((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index
                      ? {
                        progress: task.status === 'done' ? 1 : Math.max(item.progress, task.progress),
                        status:
                          task.status === 'failed'
                            ? 'failed'
                            : task.status === 'done'
                              ? 'done'
                              : 'processing',
                      }
                      : item,
                  ),
                );
                setStatusMessage(
                  `上传完成，后台处理中 ${fileLabel}：${task.status} ${Number.isFinite(percent) ? `${percent}%` : ''}`.trim(),
                );
              },
            });
            uploadedFilePaths.push(uploadResult.filePath);
          } else {
            const uploadResult = await uploadVideoToB2(currentFile, {
              onUploadProgress: (progress) => {
                setUploadProgress((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index
                      ? {
                        progress,
                        status: progress >= 1 ? 'done' : 'uploading',
                      }
                      : item,
                  ),
                );
                setStatusMessage(
                  `直传视频 ${fileLabel} 到 B2：${Math.round(progress * 100)}%`,
                );
              },
            });
            setUploadProgress((current) =>
              current.map((item, itemIndex) =>
                itemIndex === index
                  ? {
                    progress: 1,
                    status: 'done',
                  }
                  : item,
              ),
            );
            setStatusMessage(`视频 ${fileLabel} 已上传到 B2，fileId 已生成。`);
            uploadedFileIds.push(uploadResult.fileId);
          }
        }

        setStatusMessage(
          useLegacyLocalUpload
            ? '视频上传与后台预处理完成，正在创建会话...'
            : '视频已上传到 B2，正在通知后端下载并创建会话...',
        );
        const response = await createCaptionAssistantSession(
          {
            uploadedFilePaths,
            uploadedFileIds,
          },
          platform,
          normalizedPrompt,
          productManual || null,
          analysisMode,
        );

        applyAuthoritativeSession(response);
        startTransition(() => {
          setDraftPrompt('');
          setComposerMode('followup');
          setActiveDrawer(null);
        });
        upsertSessionHistory(response, normalizedPrompt);
      } catch (err) {
        setUploadProgress((current) =>
          current.map((item) =>
            item.status === 'uploading' || item.status === 'processing'
              ? { ...item, status: 'failed' }
              : item,
          ),
        );
        setPendingUserPrompt(null);
        setLoading(false);
        await handleAccessRecovery(err, '初始化对话助手失败');
        console.error('Error creating caption assistant session:', err);
      }

      return;
    }

    if (!session || !normalizedPrompt) {
      return;
    }

    setLoading(true);
    setSseTimedOut(false);
    setAccessRecoveryRequired(false);
    setError('');
    setStatusMessage('');
    setPendingUserPrompt(normalizedPrompt);

    try {
      const response = await continueCaptionAssistantSession(
        session.session_id,
        normalizedPrompt,
      );

      applyAuthoritativeSession(response);
      startTransition(() => {
        setDraftPrompt('');
        setActiveDrawer(null);
      });
    } catch (err) {
      setPendingUserPrompt(null);
      setLoading(false);
      await handleAccessRecovery(err, '继续修改失败，请重试');
      console.error('Error continuing caption assistant session:', err);
    }
  };

  const activeSessionItem = sessionHistory.find(
    (item) => item.session_id === session?.session_id,
  );
  const activeSessionTitle =
    activeSessionItem?.title ||
    session?.turns[0]?.user_prompt?.slice(0, 28) ||
    '未命名会话';
  const uploadPreviews = useMemo(
    () =>
      videos.map((video, index) => ({
        name: video.name,
        url: videoPreviewUrls[index] ?? '',
        progress: uploadProgress[index]?.progress ?? 0,
        status: uploadProgress[index]?.status ?? 'idle',
      })),
    [uploadProgress, videoPreviewUrls, videos],
  );
  const errorActions = accessRecoveryRequired ? (
    <>
      <button
        type="button"
        onClick={restartAccessLogin}
        className="inline-flex h-9 items-center justify-center rounded-full bg-rose-100 px-4 text-[12px] font-medium text-rose-950 transition hover:bg-white"
      >
        重新登录
      </button>
      <button
        type="button"
        onClick={reloadCurrentPage}
        className="inline-flex h-9 items-center justify-center rounded-full border border-rose-800/80 bg-transparent px-4 text-[12px] font-medium text-rose-100 transition hover:border-rose-700 hover:bg-rose-950/50"
      >
        仅刷新页面
      </button>
    </>
  ) : null;
  return (
    <div className="ws-shell relative h-screen min-h-0 overflow-hidden">
      <div
        className={`grid h-full min-h-0 ${historySidebarCollapsed
            ? 'lg:grid-cols-[72px_minmax(0,1fr)_368px]'
            : 'lg:grid-cols-[272px_minmax(0,1fr)_368px]'
          }`}
      >
        <HistorySidebar
          collapsed={historySidebarCollapsed}
          sessionHistory={sessionHistory}
          activeSessionId={session?.session_id}
          loadingSessionId={loadingSessionId}
          onExpand={() => setHistorySidebarCollapsed(false)}
          onCollapse={() => setHistorySidebarCollapsed(true)}
          onReset={resetSession}
          onOpenSession={(sessionId) => void openSessionFromHistory(sessionId)}
        />

        <ConversationPanel
          activeDrawer={activeDrawer}
          onToggleDrawer={(type) => setActiveDrawer((prev) => (prev === type ? null : type))}
          onCloseDrawer={() => setActiveDrawer(null)}
          sessionHistory={sessionHistory}
          activeSessionId={session?.session_id}
          loadingSessionId={loadingSessionId}
          isSessionLoading={isSessionLoading}
          onOpenSession={(sessionId) => void openSessionFromHistory(sessionId)}
          onReset={resetSession}
          threadRef={threadRef}
          session={session}
          turns={turns}
          pendingUserPrompt={pendingUserPrompt}
          isRunning={isRunning}
          submitDisabled={submitDisabled}
          draftPrompt={draftPrompt}
          setDraftPrompt={setDraftPrompt}
          submitPrompt={(value) => void submitPrompt(value)}
          analysisMode={analysisMode}
          setAnalysisMode={setAnalysisMode}
          platform={platform}
          platformOptions={PLATFORM_OPTIONS}
          setPlatform={setPlatform}
          composerMode={composerMode}
          uploadInputRef={uploadInputRef}
          uploadPreviews={uploadPreviews}
          selectedUploadIndex={selectedUploadIndex}
          onSelectUpload={setSelectedUploadIndex}
          onMoveUpload={moveUpload}
          clearUploadedVideo={clearUploadedVideo}
          productManual={productManual}
          setProductManual={setProductManual}
          sellingPointsOpen={sellingPointsOpen}
          setSellingPointsOpen={setSellingPointsOpen}
          accessRecoveryRequired={accessRecoveryRequired}
          error={
            sseTimedOut && !error
              ? 'SSE 连接 30 分钟没有新事件，已回查后台状态。任务可能仍在后台运行。'
              : error
          }
          errorActions={errorActions}
          isSubmitting={isSubmitting}
          activeSessionTitle={activeSessionTitle}
          workflowRows={workflowRows}
        />

        <WorkspaceSidebar
          session={session}
          activeSessionTitle={activeSessionTitle}
          workflowRows={workflowRows}
        />
      </div>

      <input
        ref={uploadInputRef}
        name="videos"
        type="file"
        accept="video/*"
        multiple
        className="sr-only"
        onChange={handleVideoChange}
      />
    </div>
  );
};

export default CaptionGenerator;
