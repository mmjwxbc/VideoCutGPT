import React, { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import ConversationPanel from '../components/caption-studio/ConversationPanel';
import HistorySidebar from '../components/caption-studio/HistorySidebar';
import WorkspaceSidebar from '../components/caption-studio/WorkspaceSidebar';
import {
  captionSessionEventsUrl,
  continueCaptionAssistantSession,
  createCaptionAssistantSession,
  getCaptionAssistantSession,
} from '../api/api';
import { SessionListItem, buildSessionHistoryItem, getWorkflowRows } from '../components/caption-studio/shared';
import { CaptionAssistantSession, TurnEventItem } from '../types';

const PLATFORM_OPTIONS = [
  { value: 'tiktok', label: 'TikTok', iconClassName: 'bg-slate-900' },
  { value: 'douyin', label: 'Douyin', iconClassName: 'bg-rose-500' },
  { value: 'youtube', label: 'YouTube', iconClassName: 'bg-red-500' },
  { value: 'instagram', label: 'Instagram', iconClassName: 'bg-fuchsia-500' },
];

const SSE_INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000;

const isStaleSessionVersion = (nextVersion?: number, currentVersion?: number) => {
  if (typeof nextVersion !== 'number' || typeof currentVersion !== 'number') {
    return false;
  }
  return nextVersion < currentVersion;
};

const CaptionGenerator: React.FC = () => {
  const [video, setVideo] = useState<File | null>(null);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [platform, setPlatform] = useState<string>('tiktok');
  const [productManual, setProductManual] = useState<string>('');
  const [sellingPointsOpen, setSellingPointsOpen] = useState<boolean>(false);
  const [draftPrompt, setDraftPrompt] = useState<string>(
    '请先生成适合投放的字幕初稿，并输出镜头级剪辑方案。',
  );
  const [session, setSession] = useState<CaptionAssistantSession | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [sseTimedOut, setSseTimedOut] = useState<boolean>(false);
  const [sessionHistory, setSessionHistory] = useState<SessionListItem[]>([]);
  const [composerMode, setComposerMode] = useState<'initial' | 'followup'>(
    'initial',
  );
  const [mobilePane, setMobilePane] = useState<'chat' | 'workspace'>('chat');
  const [historySidebarCollapsed, setHistorySidebarCollapsed] = useState<boolean>(false);
  const [pendingUserPrompt, setPendingUserPrompt] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const sessionRef = useRef<CaptionAssistantSession | null>(null);

  const turns = session?.turns ?? [];
  const workflowRows = useMemo(
    () => getWorkflowRows(session?.global_editing_state?.workflow),
    [session?.global_editing_state?.workflow],
  );
  const isRunning = session ? session.status === 'processing' : loading;

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  const applyAuthoritativeSession = useCallback((nextSession: CaptionAssistantSession) => {
    setPendingUserPrompt(null);
    sessionRef.current = nextSession;
    setSession((current) => {
      if (current && isStaleSessionVersion(nextSession.version, current.version)) {
        return current;
      }
      return nextSession;
    });
    setComposerMode('followup');
    setLoading(nextSession.status === 'processing');
    setError(nextSession.status === 'error' ? nextSession.error_message || '处理失败，请重试' : '');
  }, []);

  const reconcileTerminalSession = useCallback(async (sessionId: string) => {
    try {
      const latestSession = await getCaptionAssistantSession(sessionId);
      applyAuthoritativeSession(latestSession);
    } catch (err) {
      console.error('Error reconciling caption session:', err);
    }
  }, [applyAuthoritativeSession]);

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

  useEffect(() => {
    if (!session?.session_id) {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      return;
    }

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
      resetInactivityTimer();
      setSseTimedOut(false);
      const nextSession = JSON.parse(raw.data) as CaptionAssistantSession;
      applyAuthoritativeSession(nextSession);
    };

    const handleTurnEvent = (raw: MessageEvent<string>) => {
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
      resetInactivityTimer();
      setSseTimedOut(false);
    }) as EventListener);
    source.onerror = async () => {
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
    if (!video) {
      setVideoPreviewUrl(null);
      return;
    }

    const objectUrl = URL.createObjectURL(video);
    setVideoPreviewUrl(objectUrl);

    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [video]);

  const handleVideoChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] ?? null;
    setVideo(nextFile);
    event.target.value = '';
  };

  const resetSession = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    sessionRef.current = null;
    setPendingUserPrompt(null);
    setSession(null);
    setVideo(null);
    setVideoPreviewUrl(null);
    setProductManual('');
    setSellingPointsOpen(false);
    setDraftPrompt('请先生成适合投放的字幕初稿，并输出镜头级剪辑方案。');
    setComposerMode('initial');
    setLoading(false);
    setSseTimedOut(false);
    setError('');
  };

  const openSessionFromHistory = async (sessionId: string) => {
    setLoading(true);
    setError('');
    try {
      const nextSession = await getCaptionAssistantSession(sessionId);
      startTransition(() => {
        setSession(nextSession);
        setComposerMode('followup');
        setMobilePane('chat');
      });
      upsertSessionHistory(nextSession);
    } catch (err) {
      setError('读取历史会话失败，请重试');
      console.error('Error getting caption assistant session:', err);
    } finally {
      setLoading(false);
    }
  };

  const clearUploadedVideo = useCallback(() => {
    setVideo(null);
    setVideoPreviewUrl(null);
  }, []);

  const submitPrompt = async (promptValue: string) => {
    const normalizedPrompt = promptValue.trim();

    if (composerMode === 'initial') {
      if (!video) {
        setError('请先上传视频文件');
        return;
      }

      if (!normalizedPrompt) {
        setError('请输入你的首轮创作要求');
        return;
      }

      setLoading(true);
      setSseTimedOut(false);
      setError('');
      setPendingUserPrompt(normalizedPrompt);

      try {
        const response = await createCaptionAssistantSession(
          video,
          platform,
          normalizedPrompt,
          productManual || null,
        );

        applyAuthoritativeSession(response);
        startTransition(() => {
          setDraftPrompt('');
          setComposerMode('followup');
          setMobilePane('chat');
        });
        upsertSessionHistory(response, normalizedPrompt);
      } catch (err) {
        setPendingUserPrompt(null);
        setLoading(false);
        setError('初始化对话助手失败，请检查后端接口和模型配置');
        console.error('Error creating caption assistant session:', err);
      }

      return;
    }

    if (!session || !normalizedPrompt) {
      return;
    }

    setLoading(true);
    setSseTimedOut(false);
    setError('');
    setPendingUserPrompt(normalizedPrompt);

    try {
      const response = await continueCaptionAssistantSession(
        session.session_id,
        normalizedPrompt,
      );

      applyAuthoritativeSession(response);
      startTransition(() => {
        setDraftPrompt('');
        setMobilePane('chat');
      });
    } catch (err) {
      setPendingUserPrompt(null);
      setLoading(false);
      setError('继续修改失败，请重试');
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

  return (
    <div className="h-screen min-h-0 overflow-hidden bg-[#090909]">
      <div
        className={`grid h-full min-h-0 ${
          historySidebarCollapsed
            ? 'lg:grid-cols-[72px_minmax(0,1fr)_368px]'
            : 'lg:grid-cols-[272px_minmax(0,1fr)_368px]'
        }`}
      >
        <HistorySidebar
          collapsed={historySidebarCollapsed}
          sessionHistory={sessionHistory}
          activeSessionId={session?.session_id}
          onExpand={() => setHistorySidebarCollapsed(false)}
          onCollapse={() => setHistorySidebarCollapsed(true)}
          onReset={resetSession}
          onOpenSession={(sessionId) => void openSessionFromHistory(sessionId)}
        />

        <ConversationPanel
          mobilePane={mobilePane}
          setMobilePane={setMobilePane}
          threadRef={threadRef}
          session={session}
          turns={turns}
          pendingUserPrompt={pendingUserPrompt}
          isRunning={isRunning}
          draftPrompt={draftPrompt}
          setDraftPrompt={setDraftPrompt}
          submitPrompt={(value) => void submitPrompt(value)}
          platform={platform}
          platformOptions={PLATFORM_OPTIONS}
          setPlatform={setPlatform}
          composerMode={composerMode}
          uploadInputRef={uploadInputRef}
          videoPreviewUrl={videoPreviewUrl}
          videoName={video?.name ?? null}
          clearUploadedVideo={clearUploadedVideo}
          productManual={productManual}
          setProductManual={setProductManual}
          sellingPointsOpen={sellingPointsOpen}
          setSellingPointsOpen={setSellingPointsOpen}
          error={
            sseTimedOut && !error
              ? 'SSE 连接 30 分钟没有新事件，已回查后台状态。任务可能仍在后台运行。'
              : error
          }
        />

        <WorkspaceSidebar
          mobilePane={mobilePane}
          session={session}
          activeSessionTitle={activeSessionTitle}
          workflowRows={workflowRows}
        />
      </div>

      <input
        ref={uploadInputRef}
        name="video"
        type="file"
        accept="video/*"
        className="sr-only"
        onChange={handleVideoChange}
      />
    </div>
  );
};

export default CaptionGenerator;
