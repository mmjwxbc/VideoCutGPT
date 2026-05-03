import React, {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import ConversationPanel from '../components/caption-studio/ConversationPanel';
import HistorySidebar from '../components/caption-studio/HistorySidebar';
import WorkspaceSidebar from '../components/caption-studio/WorkspaceSidebar';
import {
  captionSessionEventsUrl,
  confirmCaptionAssistantPlan,
  continueCaptionAssistantSession,
  createCaptionAssistantSession,
  getCaptionAssistantSession,
} from '../api/api';
import {
  SessionListItem,
  buildSessionHistoryItem,
  formatSeconds,
  getWorkflowRows,
  groupExecutionEvents,
} from '../components/caption-studio/shared';
import {
  CaptionAssistantSession,
  ChatMessage,
  ExecutionEventItem,
  ExecutionPlanOption,
  Keyframe,
} from '../types';

const PLATFORM_OPTIONS = [
  { value: 'tiktok', label: 'TikTok', iconClassName: 'bg-slate-900' },
  { value: 'douyin', label: 'Douyin', iconClassName: 'bg-rose-500' },
  { value: 'youtube', label: 'YouTube', iconClassName: 'bg-red-500' },
  { value: 'instagram', label: 'Instagram', iconClassName: 'bg-fuchsia-500' },
];

const SNAPSHOT_EVENTS = new Set([
  'snapshot',
  'session_created',
  'message_queued',
  'plan_ready',
  'plan_confirmed',
  'completed',
  'error',
]);

const SSE_INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000;

const appendUniqueExecutionEvent = (
  current: ExecutionEventItem[],
  nextItem: ExecutionEventItem,
) => {
  const exists = current.some(
    (item) =>
      item.created_at === nextItem.created_at &&
      item.kind === nextItem.kind &&
      item.title === nextItem.title &&
      item.detail === nextItem.detail,
  );
  if (exists) {
    return current;
  }
  return [...current, nextItem];
};

const ensureAssistantMessageSlot = (
  currentMessages: ChatMessage[],
  messageIndex: number,
  createdAt: string,
) => {
  const nextMessages = [...currentMessages];
  while (nextMessages.length <= messageIndex) {
    nextMessages.push({
      role: 'assistant',
      content: '',
      created_at: createdAt,
    });
  }
  if (nextMessages[messageIndex]?.role !== 'assistant') {
    nextMessages.splice(messageIndex + 1, 0, {
      role: 'assistant',
      content: '',
      created_at: createdAt,
    });
  }
  return nextMessages;
};

const isStaleSessionVersion = (nextVersion?: number, currentVersion?: number) => {
  if (typeof nextVersion !== 'number' || typeof currentVersion !== 'number') {
    return false;
  }
  return nextVersion < currentVersion;
};

const buildAssistantReplyFromSession = (nextSession: CaptionAssistantSession) =>
  nextSession.messages[nextSession.messages.length - 1]?.content ||
  nextSession.progress_message ||
  '本轮产物已生成完成。';

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
  const [selectedKeyframe, setSelectedKeyframe] = useState<Keyframe | null>(null);
  const [sessionHistory, setSessionHistory] = useState<SessionListItem[]>([]);
  const [composerMode, setComposerMode] = useState<'initial' | 'followup'>(
    'initial',
  );
  const [mobilePane, setMobilePane] = useState<'chat' | 'workspace'>('chat');
  const [selectedPlanIds, setSelectedPlanIds] = useState<string[]>([]);
  const [historySidebarCollapsed, setHistorySidebarCollapsed] = useState<boolean>(false);
  const [pendingUserMessage, setPendingUserMessage] = useState<ChatMessage | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const sessionRef = useRef<CaptionAssistantSession | null>(null);
  const pendingSessionRef = useRef<CaptionAssistantSession | null>(null);
  const pendingSessionFlushRef = useRef<number | null>(null);

  const messages = useMemo(() => {
    const currentMessages = session?.messages ?? [];
    const optimisticMessages =
      pendingUserMessage &&
      currentMessages[currentMessages.length - 1]?.content !== pendingUserMessage.content
        ? [...currentMessages, pendingUserMessage]
        : currentMessages;
    if (!session || session.status !== 'completed') {
      return optimisticMessages;
    }
    const lastMessage = optimisticMessages[optimisticMessages.length - 1];
    if (lastMessage?.role === 'assistant' && lastMessage.content.trim()) {
      return optimisticMessages;
    }
    return [
      ...optimisticMessages,
      {
        role: 'assistant' as const,
        content: buildAssistantReplyFromSession(session),
        created_at: session.updated_at,
      },
    ];
  }, [pendingUserMessage, session]);
  const planOptions = session?.plan_options ?? [];
  const executionEvents = session?.execution_events ?? [];
  const executionGroups = useMemo(
    () => groupExecutionEvents(executionEvents),
    [executionEvents],
  );
  const workflowRows = useMemo(
    () => getWorkflowRows(session?.editing_state),
    [session?.editing_state],
  );
  const isRunning = session
    ? session.status === 'queued' ||
      session.status === 'planning' ||
      session.status === 'processing'
    : loading;
  const progressText = useMemo(() => {
    if (!session) {
      return '处理中…';
    }
    if (
      sseTimedOut &&
      (session.status === 'queued' ||
        session.status === 'planning' ||
        session.status === 'processing')
    ) {
      return 'SSE 连接 30 分钟没有新事件，已回查后台状态。任务可能仍在后台运行。';
    }
    if (session.status === 'completed') {
      if (
        session.progress_message &&
        !session.progress_message.startsWith('Agent 正在')
      ) {
        return session.progress_message;
      }
      return session.selected_plan_ids.length ? '所选执行项已完成。' : '本轮修改完成。';
    }
    if (session.status === 'error') {
      return session.error_message || '处理失败。';
    }
    return session.progress_message || '处理中…';
  }, [session, sseTimedOut]);
  const currentExecutionGroup =
    executionGroups.length > 0 ? executionGroups[executionGroups.length - 1] : null;
  const hasWorkspaceReply = Boolean(
    session?.plan_options?.length ||
    session?.execution_events?.length ||
    session?.agent_trace?.length ||
    session?.execution_plan?.length ||
    workflowRows.length,
  );

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  const clearPendingSessionFlush = useCallback(() => {
    if (pendingSessionFlushRef.current !== null) {
      window.clearTimeout(pendingSessionFlushRef.current);
      pendingSessionFlushRef.current = null;
    }
    pendingSessionRef.current = null;
  }, []);

  const scheduleSessionMerge = useCallback(
    (updater: (current: CaptionAssistantSession | null) => CaptionAssistantSession | null) => {
      const currentBase = pendingSessionRef.current ?? sessionRef.current;
      const nextSession = updater(currentBase);
      if (!nextSession) {
        return;
      }

      pendingSessionRef.current = nextSession;
      if (pendingSessionFlushRef.current !== null) {
        return;
      }

      pendingSessionFlushRef.current = window.setTimeout(() => {
        pendingSessionFlushRef.current = null;
        const pendingSession = pendingSessionRef.current;
        pendingSessionRef.current = null;
        if (!pendingSession) {
          return;
        }
        sessionRef.current = pendingSession;
        startTransition(() => {
          setSession(pendingSession);
        });
      }, 120);
    },
    [],
  );

  const applyAuthoritativeSession = (nextSession: CaptionAssistantSession) => {
    const commitSession = () => {
      clearPendingSessionFlush();
      sessionRef.current = nextSession;
      setPendingUserMessage(null);
      setSession((current) => {
        if (nextSession.status === 'completed' || nextSession.status === 'error') {
          if (current && isStaleSessionVersion(nextSession.version, current.version)) {
            return current;
          }
          return nextSession;
        }
        if (current && isStaleSessionVersion(nextSession.version, current.version)) {
          return current;
        }
        return nextSession;
      });
      setComposerMode('followup');
      if (nextSession.status === 'completed' || nextSession.status === 'error') {
        setMobilePane('chat');
      }
      setLoading(
        nextSession.status === 'queued' ||
          nextSession.status === 'planning' ||
          nextSession.status === 'processing',
      );
      setError(
        nextSession.status === 'error'
          ? nextSession.error_message || '处理失败，请重试'
          : '',
      );
    };

    if (nextSession.status === 'completed' || nextSession.status === 'error') {
      commitSession();
      return;
    }

    startTransition(commitSession);
  };

  const reconcileTerminalSession = useCallback(async (sessionId: string) => {
    try {
      const latestSession = await getCaptionAssistantSession(sessionId);
      applyAuthoritativeSession(latestSession);
    } catch (err) {
      console.error('Error reconciling terminal caption session:', err);
    }
  }, []);

  const upsertSessionHistory = (
    nextSession: CaptionAssistantSession,
    fallbackTitle?: string,
  ) => {
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
  };

  useEffect(() => {
    if (!session) {
      setSelectedPlanIds([]);
      return;
    }

    if (session.status !== 'awaiting_plan_selection') {
      setSelectedPlanIds(session.selected_plan_ids ?? []);
      return;
    }

    const defaults = session.plan_options
      .filter((option) => option.required || option.selected)
      .map((option) => option.id);
    setSelectedPlanIds(defaults);
  }, [session]);

  useEffect(() => {
    if (!session) {
      return;
    }
    upsertSessionHistory(session);
  }, [session]);

  useEffect(() => {
    if (!session) {
      return;
    }
    if (
      session.status !== 'queued' &&
      session.status !== 'planning' &&
      session.status !== 'processing'
    ) {
      setLoading(false);
    }
  }, [session]);

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
        try {
          const latestSession = await getCaptionAssistantSession(session.session_id);
          applyAuthoritativeSession(latestSession);
        } catch (err) {
          console.error('Error checking caption session after SSE timeout:', err);
        }
      }, SSE_INACTIVITY_TIMEOUT_MS);
    };

    const handleSnapshot = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const nextSession = JSON.parse(raw.data) as CaptionAssistantSession;
      applyAuthoritativeSession(nextSession);
    };

    const handleProgress = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        status: CaptionAssistantSession['status'];
        message: string;
        version: number;
        updated_at: string;
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
          status: payload.status,
          progress_message: payload.message,
          version: payload.version,
          updated_at: payload.updated_at,
        };
      });
      setLoading(
        payload.status === 'queued' ||
          payload.status === 'planning' ||
          payload.status === 'processing',
      );
    };

    const handleExecutionEvent = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        version: number;
        kind: string;
        title: string;
        detail: string;
        tool: string;
        artifact: string;
        created_at: string;
      };
      scheduleSessionMerge((current) => {
        if (!current) {
          return current;
        }
        if (isStaleSessionVersion(payload.version, current.version)) {
          return current;
        }
        return {
          ...current,
          version: payload.version,
          execution_events: appendUniqueExecutionEvent(current.execution_events ?? [], payload),
        };
      });
    };

    const handleArtifactUpdated = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        artifact: string;
        value: unknown;
        version: number;
        updated_at: string;
      };
      scheduleSessionMerge((current) => {
        if (!current) {
          return current;
        }
        if (isStaleSessionVersion(payload.version, current.version)) {
          return current;
        }
        const nextSession: CaptionAssistantSession = {
          ...current,
          version: payload.version,
          updated_at: payload.updated_at,
        };
        if (payload.artifact === 'keyframes') {
          nextSession.keyframes = Array.isArray(payload.value) ? (payload.value as Keyframe[]) : current.keyframes;
        } else if (payload.artifact === 'frame_analyses') {
          nextSession.frame_analyses = Array.isArray(payload.value) ? (payload.value as string[]) : current.frame_analyses;
        } else if (payload.artifact === 'video_summary') {
          nextSession.video_summary = typeof payload.value === 'string' ? payload.value : current.video_summary;
        } else if (payload.artifact === 'subtitle_draft') {
          nextSession.subtitle_draft = typeof payload.value === 'string' ? payload.value : current.subtitle_draft;
        } else if (payload.artifact === 'editing_plan') {
          nextSession.editing_plan = typeof payload.value === 'string' ? payload.value : current.editing_plan;
        } else if (payload.artifact === 'english_title') {
          nextSession.english_title = typeof payload.value === 'string' ? payload.value : current.english_title;
        } else if (payload.artifact === 'tags') {
          nextSession.tags = Array.isArray(payload.value) ? (payload.value as string[]) : current.tags;
        }
        return nextSession;
      });
    };

    const handleArtifactChunk = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        artifact: string;
        content: string;
        version: number;
        updated_at: string;
      };
      scheduleSessionMerge((current) => {
        if (!current) {
          return current;
        }
        if (isStaleSessionVersion(payload.version, current.version)) {
          return current;
        }
        const nextSession: CaptionAssistantSession = {
          ...current,
          version: payload.version,
          updated_at: payload.updated_at,
        };
        if (payload.artifact === 'video_summary') {
          nextSession.video_summary = payload.content;
        } else if (payload.artifact === 'subtitle_draft') {
          nextSession.subtitle_draft = payload.content;
        } else if (payload.artifact === 'editing_plan') {
          nextSession.editing_plan = payload.content;
        } else if (payload.artifact === 'english_title') {
          nextSession.english_title = payload.content;
        }
        return nextSession;
      });
    };

    const handleMessageChunk = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        message_index: number;
        content: string;
        version: number;
        updated_at: string;
      };
      scheduleSessionMerge((current) => {
        if (!current) {
          return current;
        }
        if (isStaleSessionVersion(payload.version, current.version)) {
          return current;
        }
        const nextMessages = ensureAssistantMessageSlot(
          current.messages,
          payload.message_index,
          payload.updated_at,
        );
        if (payload.message_index >= 0 && payload.message_index < nextMessages.length) {
          nextMessages[payload.message_index] = {
            ...nextMessages[payload.message_index],
            role: 'assistant',
            content: payload.content,
            created_at:
              nextMessages[payload.message_index]?.created_at || payload.updated_at,
          };
        }
        return {
          ...current,
          messages: nextMessages,
          version: payload.version,
          updated_at: payload.updated_at,
        };
      });
    };

    const handlePlannerChunk = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        content: string;
        version: number;
        updated_at: string;
      };
      scheduleSessionMerge((current) => {
        if (!current) {
          return current;
        }
        if (isStaleSessionVersion(payload.version, current.version)) {
          return current;
        }
        return {
          ...current,
          planner_stream: payload.content,
          version: payload.version,
          updated_at: payload.updated_at,
        };
      });
    };

    const handlePing = () => {
      resetInactivityTimer();
      setSseTimedOut(false);
    };

    for (const eventName of SNAPSHOT_EVENTS) {
      source.addEventListener(eventName, handleSnapshot as EventListener);
    }
    source.addEventListener('progress', handleProgress as EventListener);
    source.addEventListener('execution_event', handleExecutionEvent as EventListener);
    source.addEventListener('artifact_updated', handleArtifactUpdated as EventListener);
    source.addEventListener('artifact_chunk', handleArtifactChunk as EventListener);
    source.addEventListener('message_chunk', handleMessageChunk as EventListener);
    source.addEventListener('planner_chunk', handlePlannerChunk as EventListener);
    source.addEventListener('ping', handlePing as EventListener);
    source.onerror = async () => {
      console.error('Caption SSE connection interrupted.');
      clearInactivityTimer();
      try {
        const latestSession = await getCaptionAssistantSession(session.session_id);
        applyAuthoritativeSession(latestSession);
        if (eventSourceRef.current === source) {
          resetInactivityTimer();
        }
      } catch (err) {
        console.error('Error reconciling caption session after SSE interruption:', err);
        if (eventSourceRef.current === source) {
          resetInactivityTimer();
        }
      }
    };
    resetInactivityTimer();

    return () => {
      closeSource();
    };
  }, [clearPendingSessionFlush, scheduleSessionMerge, session?.session_id]);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) {
      return;
    }
    thread.scrollTop = thread.scrollHeight;
  }, [messages.length, progressText, session?.updated_at]);

  useEffect(() => {
    if (!session?.session_id) {
      return;
    }
    if (session.status !== 'completed' && session.status !== 'error') {
      return;
    }
    const hasAssistantReply = session.messages.some(
      (message) => message.role === 'assistant' && message.content.trim(),
    );
    if (hasAssistantReply) {
      return;
    }
    void reconcileTerminalSession(session.session_id);
  }, [session, reconcileTerminalSession]);

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
    clearPendingSessionFlush();
    sessionRef.current = null;
    setPendingUserMessage(null);
    setSession(null);
    setVideo(null);
    setVideoPreviewUrl(null);
    setProductManual('');
    setSellingPointsOpen(false);
    setDraftPrompt('请先生成适合投放的字幕初稿，并输出镜头级剪辑方案。');
    setComposerMode('initial');
    setSelectedPlanIds([]);
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
        setLoading(false);
        setError('初始化对话助手失败，请检查后端接口和模型配置');
        console.error('Error creating caption assistant session:', err);
      }

      return;
    }

    if (session?.status === 'awaiting_plan_selection') {
      setError('请先确认 Agent 执行计划，再继续发送改稿指令');
      return;
    }

    if (!session || !normalizedPrompt) {
      return;
    }

    setLoading(true);
    setSseTimedOut(false);
    setError('');
    setPendingUserMessage({
      role: 'user',
      content: normalizedPrompt,
      created_at: new Date().toISOString(),
    });

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
      setPendingUserMessage(null);
      setLoading(false);
      setError('继续修改失败，请重试');
      console.error('Error continuing caption assistant session:', err);
    }
  };

  const togglePlanOption = (option: ExecutionPlanOption) => {
    if (option.required) {
      return;
    }

    setSelectedPlanIds((current) =>
      current.includes(option.id)
        ? current.filter((item) => item !== option.id)
        : [...current, option.id],
    );
  };

  const handleConfirmPlan = async () => {
    if (!session) {
      return;
    }

    const requiredIds = planOptions
      .filter((option) => option.required)
      .map((option) => option.id);
    const nextIds = Array.from(new Set([...selectedPlanIds, ...requiredIds]));

    if (!requiredIds.every((id) => nextIds.includes(id))) {
      setError('关键帧分析是必选项，不能取消');
      return;
    }

    setLoading(true);
    setSseTimedOut(false);
    setError('');

    try {
      const response = await confirmCaptionAssistantPlan(session.session_id, nextIds);
      applyAuthoritativeSession(response);
      startTransition(() => {
        setMobilePane('workspace');
      });
    } catch (err) {
      setLoading(false);
      setError('确认执行计划失败，请重试');
      console.error('Error confirming caption assistant plan:', err);
    }
  };

  const activeSessionItem = sessionHistory.find(
    (item) => item.session_id === session?.session_id,
  );
  const activeSessionTitle =
    activeSessionItem?.title ||
    session?.messages.find((message) => message.role === 'user')?.content?.slice(0, 28) ||
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
          messages={messages}
          isRunning={isRunning}
          progressText={progressText}
          executionGroups={executionGroups}
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
          error={error}
        />

        <WorkspaceSidebar
          mobilePane={mobilePane}
          session={session}
          activeSessionTitle={activeSessionTitle}
          progressText={progressText}
          hasWorkspaceReply={hasWorkspaceReply}
          planOptions={planOptions}
          selectedPlanIds={selectedPlanIds}
          togglePlanOption={togglePlanOption}
          currentExecutionGroup={currentExecutionGroup}
          isRunning={isRunning}
          workflowRows={workflowRows}
          onConfirmPlan={() => void handleConfirmPlan()}
        />
      </div>

      {selectedKeyframe ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
          onClick={() => setSelectedKeyframe(null)}
        >
          <div
            className="max-h-[90vh] max-w-4xl overflow-hidden rounded-[28px] border border-slate-700 bg-[#111111] shadow-[0_30px_100px_rgba(0,0,0,0.45)]"
            onClick={(event) => event.stopPropagation()}
          >
            <img
              src={`data:image/jpeg;base64,${selectedKeyframe.image_base64}`}
              alt="关键帧预览"
              className="max-h-[78vh] w-full object-contain bg-slate-950"
            />
            <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 text-sm text-slate-300">
              <div>
                预览图 · {formatSeconds(selectedKeyframe.timestamp_seconds)} ·{' '}
                {selectedKeyframe.source}
              </div>
              <button
                type="button"
                onClick={() => setSelectedKeyframe(null)}
                className="rounded-full border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-600"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      ) : null}

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
