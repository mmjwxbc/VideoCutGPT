import React, {
  startTransition,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUp,
  Bot,
  ChevronDown,
  Clapperboard,
  Film,
  RefreshCcw,
  Sparkles,
  User,
} from 'lucide-react';

import { Button } from '../components/ui/button';
import {
  captionSessionEventsUrl,
  confirmCaptionAssistantPlan,
  continueCaptionAssistantSession,
  createCaptionAssistantSession,
  getCaptionAssistantSession,
} from '../api/api';
import {
  CaptionAssistantSession,
  ChatMessage,
  ExecutionEventItem,
  ExecutionPlanOption,
  Keyframe,
} from '../types';

const PLATFORM_OPTIONS = [
  { value: 'tiktok', label: 'TikTok' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'facebook', label: 'Facebook' },
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

const SSE_INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000;

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

const getSessionStatusRank = (status: CaptionAssistantSession['status']) => {
  switch (status) {
    case 'idle':
      return 0;
    case 'queued':
      return 1;
    case 'planning':
      return 2;
    case 'awaiting_plan_selection':
      return 3;
    case 'processing':
      return 4;
    case 'completed':
      return 5;
    case 'error':
      return 6;
    default:
      return 0;
  }
};

const isOlderTimestamp = (nextValue?: string, currentValue?: string) => {
  if (!nextValue || !currentValue) {
    return false;
  }
  return new Date(nextValue).getTime() < new Date(currentValue).getTime();
};

const buildAssistantReplyFromSession = (nextSession: CaptionAssistantSession) => {
  const sections: string[] = [];
  if (nextSession.video_summary.trim()) {
    sections.push(`视频摘要：\n${nextSession.video_summary.trim()}`);
  }
  if (nextSession.subtitle_draft.trim()) {
    sections.push(`字幕草稿：\n${nextSession.subtitle_draft.trim()}`);
  }
  if (nextSession.editing_plan.trim()) {
    sections.push(`剪辑方案：\n${nextSession.editing_plan.trim()}`);
  }
  if (nextSession.english_title.trim()) {
    sections.push(`英文标题：\n${nextSession.english_title.trim()}`);
  }
  if (nextSession.tags.length) {
    sections.push(`标签：\n${nextSession.tags.map((tag) => `- ${tag}`).join('\n')}`);
  }
  return sections.join('\n\n') || nextSession.progress_message || '本轮产物已生成完成。';
};

const panelClassName =
  'rounded-[22px] border border-white/70 bg-white/80 shadow-[0_16px_42px_rgba(15,23,42,0.08)] backdrop-blur-xl';

const formatTimestamp = (value: string) =>
  new Date(value).toLocaleString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    month: 'numeric',
    day: 'numeric',
  });

const formatSeconds = (value: number) => {
  const totalSeconds = Math.max(0, Math.floor(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds
    .toString()
    .padStart(2, '0')}`;
};

interface PanelProps {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  hideHeader?: boolean;
}

interface ChatBubbleProps {
  message: ChatMessage;
}

interface WorkflowStepCardProps {
  title: string;
  status: 'pending' | 'active' | 'completed';
  children: React.ReactNode;
  defaultOpen?: boolean;
}

interface SessionListItem {
  session_id: string;
  title: string;
  subtitle: string;
  updated_at: string;
  status: CaptionAssistantSession['status'];
}

interface ExecutionGroup {
  parent: ExecutionEventItem;
  children: ExecutionEventItem[];
}

interface ArtifactCardProps {
  title: string;
  content: string;
  defaultOpen?: boolean;
}

const groupExecutionEvents = (events: ExecutionEventItem[]): ExecutionGroup[] => {
  const groups: ExecutionGroup[] = [];
  let currentGroup: ExecutionGroup | null = null;

  for (const item of events) {
    if (item.kind === 'tool_started') {
      currentGroup = { parent: item, children: [] };
      groups.push(currentGroup);
      continue;
    }

    if (!currentGroup) {
      currentGroup = {
        parent: {
          kind: 'tool_started',
          title: '执行事件',
          detail: '系统执行记录',
          tool: item.tool,
          artifact: item.artifact,
          created_at: item.created_at,
        },
        children: [],
      };
      groups.push(currentGroup);
    }

    currentGroup.children.push(item);
    if (item.kind === 'tool_completed') {
      currentGroup = null;
    }
  }

  return groups;
};

const Panel: React.FC<PanelProps> = ({
  title,
  eyebrow,
  children,
  className = '',
  bodyClassName = '',
  hideHeader = false,
}) => (
  <section className={`${panelClassName} flex min-h-0 flex-col ${className}`}>
    {hideHeader ? null : (
      <div className="border-b border-slate-100 px-3.5 py-2.5">
        {eyebrow ? (
          <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-slate-400">
            {eyebrow}
          </p>
        ) : null}
        <h2 className={`text-[13px] font-semibold text-slate-900 ${eyebrow ? 'mt-1.5' : ''}`}>
          {title}
        </h2>
      </div>
    )}
    <div className={`min-h-0 px-3.5 py-3 ${bodyClassName}`}>{children}</div>
  </section>
);

const ChatBubble: React.FC<ChatBubbleProps> = ({ message }) => {
  const isAssistant = message.role === 'assistant';

  return (
    <article
      className={`flex w-full items-start gap-2.5 ${
        isAssistant ? 'justify-start pr-3 sm:pr-8' : 'justify-end pl-10 sm:pl-24'
      }`}
    >
      {isAssistant ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white shadow-sm">
          <Bot className="h-3 w-3" />
        </div>
      ) : null}

      <div
        className={`w-fit min-w-0 rounded-2xl px-3 py-2.5 shadow-[0_10px_24px_rgba(15,23,42,0.06)] ${
          isAssistant
            ? 'max-w-[min(92%,52rem)] border border-slate-200 bg-white text-slate-700'
            : 'max-w-[min(72%,34rem)] bg-slate-900 text-white'
          }`}
      >
        <div className="mb-1 flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
          <span className={isAssistant ? 'text-slate-400' : 'text-white/60'}>
            {isAssistant ? 'Assistant' : 'You'}
          </span>
        </div>
        <p className="whitespace-pre-wrap break-words text-[12px] leading-5">
          {message.content}
        </p>
      </div>

      {!isAssistant ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm">
          <User className="h-3 w-3" />
        </div>
      ) : null}
    </article>
  );
};

const WorkflowStepCard: React.FC<WorkflowStepCardProps> = ({
  title,
  status,
  children,
  defaultOpen = false,
}) => {
  const statusClassName =
    status === 'completed'
      ? 'bg-emerald-500'
      : status === 'active'
        ? 'bg-sky-500'
        : 'bg-slate-300';

  const statusLabel =
    status === 'completed' ? '已完成' : status === 'active' ? '进行中' : '等待中';

  return (
    <details
      open={defaultOpen}
      className="group rounded-[18px] border border-slate-200 bg-slate-50/80"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2.5 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${statusClassName}`} />
          <h4 className="truncate text-[13px] font-medium text-slate-900">{title}</h4>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="text-[10px] uppercase tracking-[0.22em] text-slate-400">
            {statusLabel}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-slate-400 transition group-open:rotate-180" />
        </div>
      </summary>
      <div className="border-t border-slate-200 px-3 py-2.5 text-[13px] leading-5 text-slate-600">
        {children}
      </div>
    </details>
  );
};

const ArtifactCard: React.FC<ArtifactCardProps> = ({
  title,
  content,
  defaultOpen = true,
}) => (
  <details
    open={defaultOpen}
    className="group rounded-[18px] border border-slate-200 bg-white/92"
  >
    <summary className="flex cursor-pointer list-none items-center justify-between gap-2.5 px-3 py-2.5">
      <h4 className="truncate text-[13px] font-medium text-slate-900">{title}</h4>
      <ChevronDown className="h-3.5 w-3.5 text-slate-400 transition group-open:rotate-180" />
    </summary>
    <div className="border-t border-slate-200 px-3 py-2.5">
      <pre className="whitespace-pre-wrap break-words font-sans text-[12px] leading-5 text-slate-700">
        {content}
      </pre>
    </div>
  </details>
);

const CaptionGenerator: React.FC = () => {
  const [video, setVideo] = useState<File | null>(null);
  const [platform, setPlatform] = useState<string>('tiktok');
  const [productManual, setProductManual] = useState<string>('');
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
  const threadRef = useRef<HTMLDivElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const messages = useMemo(() => {
    const currentMessages = session?.messages ?? [];
    if (!session || session.status !== 'completed') {
      return currentMessages;
    }
    const hasCompletedAssistantReply = currentMessages.some(
      (message) => message.role === 'assistant' && message.content.trim(),
    );
    if (hasCompletedAssistantReply) {
      return currentMessages;
    }
    return [
      ...currentMessages,
      {
        role: 'assistant' as const,
        content: buildAssistantReplyFromSession(session),
        created_at: session.updated_at,
      },
    ];
  }, [session]);
  const planOptions = session?.plan_options ?? [];
  const executionEvents = session?.execution_events ?? [];
  const executionGroups = useMemo(
    () => groupExecutionEvents(executionEvents),
    [executionEvents],
  );
  const draftPreview = useMemo(() => draftPrompt.trim(), [draftPrompt]);
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
      return 'SSE 连接 5 分钟没有新事件，已回查后台状态。任务可能仍在后台运行。';
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
  const showExecutionReplyInChat = isRunning;
  const hasWorkspaceReply = Boolean(
    session?.plan_options?.length ||
    session?.execution_events?.length ||
    session?.agent_trace?.length ||
    session?.keyframes?.length ||
    session?.video_summary ||
    session?.execution_plan?.length ||
    session?.subtitle_draft ||
    session?.editing_plan ||
    session?.english_title ||
    session?.tags?.length,
  );

  const applyAuthoritativeSession = (nextSession: CaptionAssistantSession) => {
    const commitSession = () => {
      setSession((current) => {
        if (nextSession.status === 'completed' || nextSession.status === 'error') {
          return nextSession;
        }
        if (current && isOlderTimestamp(nextSession.updated_at, current.updated_at)) {
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
      upsertSessionHistory(nextSession);
    };

    if (nextSession.status === 'completed' || nextSession.status === 'error') {
      commitSession();
      return;
    }

    startTransition(commitSession);
  };

  const upsertSessionHistory = (
    nextSession: CaptionAssistantSession,
    fallbackTitle?: string,
  ) => {
    const titleSource =
      fallbackTitle ||
      nextSession.messages.find((message) => message.role === 'user')?.content ||
      '未命名会话';
    const title = titleSource.trim().slice(0, 28) || '未命名会话';
    const subtitle =
      nextSession.progress_message ||
      nextSession.video_summary ||
      nextSession.messages[nextSession.messages.length - 1]?.content ||
      '等待处理';

    setSessionHistory((current) => {
      const nextItem: SessionListItem = {
        session_id: nextSession.session_id,
        title,
        subtitle: subtitle.trim().slice(0, 42) || '等待处理',
        updated_at: nextSession.updated_at,
        status: nextSession.status,
      };
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
        setError('SSE 连接 5 分钟没有新事件，已停止等待并回查后台状态。');
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
      if (nextSession.status === 'completed' || nextSession.status === 'error') {
        closeSource();
      }
      applyAuthoritativeSession(nextSession);
    };

    const handleProgress = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        status: CaptionAssistantSession['status'];
        message: string;
        updated_at: string;
      };
      setSession((current) => {
        if (!current) {
          return current;
        }
        if (current.status === 'completed' || current.status === 'error') {
          return current;
        }
        if (isOlderTimestamp(payload.updated_at, current.updated_at)) {
          return current;
        }
        if (
          getSessionStatusRank(current.status) >= getSessionStatusRank('completed') &&
          getSessionStatusRank(payload.status) < getSessionStatusRank(current.status)
        ) {
          return current;
        }
        return {
          ...current,
          status: payload.status,
          progress_message: payload.message,
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
        kind: string;
        title: string;
        detail: string;
        tool: string;
        artifact: string;
        created_at: string;
      };
      setSession((current) =>
        current && current.status !== 'completed' && current.status !== 'error'
          ? {
              ...current,
              execution_events: appendUniqueExecutionEvent(current.execution_events ?? [], payload),
            }
          : current,
      );
    };

    const handleArtifactUpdated = (raw: MessageEvent<string>) => {
      resetInactivityTimer();
      setSseTimedOut(false);
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        artifact: string;
        value: unknown;
        updated_at: string;
      };
      setSession((current) => {
        if (!current) {
          return current;
        }
        if (current.status === 'completed' || current.status === 'error') {
          return current;
        }
        if (isOlderTimestamp(payload.updated_at, current.updated_at)) {
          return current;
        }
        const nextSession: CaptionAssistantSession = {
          ...current,
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
        updated_at: string;
      };
      setSession((current) => {
        if (!current) {
          return current;
        }
        if (current.status === 'completed' || current.status === 'error') {
          return current;
        }
        if (isOlderTimestamp(payload.updated_at, current.updated_at)) {
          return current;
        }
        const nextSession: CaptionAssistantSession = {
          ...current,
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
        updated_at: string;
      };
      setSession((current) => {
        if (!current) {
          return current;
        }
        if (current.status === 'completed' || current.status === 'error') {
          return current;
        }
        if (isOlderTimestamp(payload.updated_at, current.updated_at)) {
          return current;
        }
        const nextMessages = [...current.messages];
        if (payload.message_index >= 0 && payload.message_index < nextMessages.length) {
          nextMessages[payload.message_index] = {
            ...nextMessages[payload.message_index],
            content: payload.content,
          };
        }
        return {
          ...current,
          messages: nextMessages,
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
    source.addEventListener('ping', handlePing as EventListener);
    source.onerror = async () => {
      console.error('Caption SSE connection interrupted.');
      clearInactivityTimer();
      try {
        const latestSession = await getCaptionAssistantSession(session.session_id);
        applyAuthoritativeSession(latestSession);
        if (latestSession.status === 'completed' || latestSession.status === 'error') {
          closeSource();
        } else if (eventSourceRef.current === source) {
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
  }, [session?.session_id]);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) {
      return;
    }
    thread.scrollTop = thread.scrollHeight;
  }, [messages.length, progressText, session?.updated_at]);

  const handleVideoChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] ?? null;
    setVideo(nextFile);
  };

  const resetSession = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setSession(null);
    setVideo(null);
    setProductManual('');
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

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (composerMode === 'initial') {
      if (!video) {
        setError('请先上传视频文件');
        return;
      }

      if (!draftPreview) {
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
          draftPreview,
          productManual || null,
        );

        startTransition(() => {
          setSession(response);
          setDraftPrompt('');
          setComposerMode('followup');
          setMobilePane('chat');
        });
        upsertSessionHistory(response, draftPreview);
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

    if (!session || !draftPreview) {
      return;
    }

    setLoading(true);
    setSseTimedOut(false);
    setError('');

    try {
      const response = await continueCaptionAssistantSession(
        session.session_id,
        draftPreview,
      );

      startTransition(() => {
        setSession(response);
        setDraftPrompt('');
        setMobilePane('chat');
      });
      upsertSessionHistory(response);
    } catch (err) {
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
      startTransition(() => {
        setSession(response);
        setMobilePane('workspace');
      });
      upsertSessionHistory(response);
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
    <div className="relative flex h-full min-h-0 overflow-hidden bg-[linear-gradient(180deg,#eef4ff_0%,#fbfdff_42%,#f6efe6_100%)] p-2 md:p-2.5">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-8%] top-[-12%] h-64 w-64 rounded-full bg-sky-300/25 blur-3xl" />
        <div className="absolute right-[-6%] top-[12%] h-72 w-72 rounded-full bg-amber-300/20 blur-3xl" />
        <div className="absolute bottom-[-10%] left-[34%] h-64 w-64 rounded-full bg-emerald-200/20 blur-3xl" />
      </div>

      <div className="relative mx-auto flex h-full min-h-0 w-full max-w-[1400px] flex-col overflow-hidden rounded-[24px] border border-white/60 bg-white/35 shadow-[0_24px_72px_rgba(15,23,42,0.10)] backdrop-blur-2xl">
        <div className="grid flex-1 gap-2 overflow-hidden p-2 xl:grid-cols-[252px_minmax(500px,1fr)_360px] 2xl:grid-cols-[252px_minmax(540px,1fr)_376px]">
          <aside className="min-h-0 overflow-hidden">
            <Panel
              title=""
              className="h-full overflow-hidden"
              bodyClassName="flex min-h-0 flex-1 flex-col"
              hideHeader
            >
              <div className="mb-3 flex shrink-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">
                    <Clapperboard className="h-3 w-3" />
                    Caption Studio
                  </div>
                  <h1 className="mt-1 text-[17px] font-semibold text-slate-950">
                    桌面工作台
                  </h1>
                </div>
                <Link
                  to="/"
                  className="shrink-0 rounded-full border border-slate-200 bg-white/85 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-950"
                >
                  返回
                </Link>
              </div>

              <Button
                type="button"
                variant="outline"
                className="mb-3 w-full"
                onClick={resetSession}
              >
                <RefreshCcw className="mr-2 h-4 w-4" />
                新建任务
              </Button>

              {/* <div className="mb-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-500">
                历史会话单独滚动，右侧工作区不会因为会话列表过长而压缩。
              </div> */}

              <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                <div className="space-y-2">
                  {sessionHistory.length ? (
                    sessionHistory.map((item) => {
                      const isActive = session?.session_id === item.session_id;
                      return (
                        <button
                          key={item.session_id}
                          type="button"
                          onClick={() => void openSessionFromHistory(item.session_id)}
                          className={`w-full rounded-2xl border px-3 py-3 text-left transition ${isActive
                              ? 'border-sky-300 bg-sky-50 shadow-sm'
                              : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'
                            }`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <p className="truncate text-sm font-medium text-slate-900">
                              {item.title}
                            </p>
                            <span className="rounded-full bg-white px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-400">
                              {item.status}
                            </span>
                          </div>
                          <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">
                            {item.subtitle}
                          </p>
                          <p className="mt-2 text-[11px] text-slate-400">
                            {formatTimestamp(item.updated_at)}
                          </p>
                        </button>
                      );
                    })
                  ) : (
                    <div className="rounded-[18px] border border-dashed border-slate-200 bg-slate-50 px-3.5 py-4 text-[13px] leading-5 text-slate-500">
                      还没有历史会话。创建首轮任务后，后续所有版本都会沉淀在这里。
                    </div>
                  )}
                </div>
              </div>
            </Panel>
          </aside>

          <section className="flex min-h-0 flex-col gap-3 overflow-visible xl:overflow-hidden">
            <div className="flex items-center gap-2 xl:hidden">
              <button
                type="button"
                onClick={() => setMobilePane('chat')}
                className={`inline-flex h-8 flex-1 items-center justify-center rounded-full border text-[12px] font-medium transition ${
                  mobilePane === 'chat'
                    ? 'border-sky-300 bg-sky-50 text-sky-700'
                    : 'border-slate-200 bg-white/80 text-slate-600'
                }`}
              >
                聊天记录
              </button>
              <button
                type="button"
                onClick={() => setMobilePane('workspace')}
                className={`inline-flex h-8 flex-1 items-center justify-center rounded-full border text-[12px] font-medium transition ${
                  mobilePane === 'workspace'
                    ? 'border-sky-300 bg-sky-50 text-sky-700'
                    : 'border-slate-200 bg-white/80 text-slate-600'
                }`}
              >
                执行工作区
              </button>
            </div>

            <Panel
              title="对话记录"
              eyebrow="Conversation"
              className={`min-h-0 flex-1 overflow-hidden ${mobilePane === 'workspace' ? 'hidden xl:block' : ''}`}
              bodyClassName="flex min-h-0 flex-1 flex-col"
            >
              <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 [overflow-anchor:none]">
                <div className="flex min-h-full flex-col gap-2.5 pb-5">
                  {!session ? (
                    <div className="flex min-h-[160px] items-center justify-center rounded-[18px] border border-slate-200 bg-slate-50/70 px-3.5 py-4 text-center">
                      <div className="max-w-lg">
                        <p className="text-[10px] font-medium uppercase tracking-[0.24em] text-slate-400">
                          Waiting For Session
                        </p>
                        <h3 className="mt-2 text-[15px] font-semibold tracking-[-0.04em] text-slate-900">
                          先在下方创建你的第一轮任务
                        </h3>
                        <p className="mt-2 text-[12px] leading-5 text-slate-600">
                          提交后，这里会持续显示用户要求、助手回复和后续每一轮改稿指令。
                        </p>
                      </div>
                    </div>
                  ) : (
                    messages.map((message, index) => (
                      <ChatBubble
                        key={`${message.created_at}-${index}`}
                        message={message}
                      />
                    ))
                  )}

                  {showExecutionReplyInChat ? (
                    <article className="flex w-full items-start gap-2.5 justify-start pr-16">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white shadow-sm">
                        <Bot className="h-3 w-3" />
                      </div>
                      <details
                        open
                        className="group w-fit min-w-0 max-w-[min(72%,34rem)] rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-[0_10px_24px_rgba(15,23,42,0.06)]"
                      >
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span
                                className={`h-2 w-2 rounded-full ${
                                  isRunning ? 'bg-sky-500' : 'bg-emerald-500'
                                }`}
                              />
                              <p className="truncate text-[12px] font-medium text-slate-900">
                                Assistant 执行回复
                              </p>
                            </div>
                            <p className="mt-1 break-words text-[11px] leading-4 text-slate-500">
                              {isRunning
                                ? progressText
                                : `${executionGroups.length} 个工具步骤，点击展开查看完整执行树`}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <span className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
                              {isRunning ? '进行中' : '已完成'}
                            </span>
                            <ChevronDown className="h-3.5 w-3.5 text-slate-400 transition group-open:rotate-180" />
                          </div>
                        </summary>
                        <div className="border-t border-slate-200 px-3 py-2.5">
                          {isRunning ? (
                            <div className="mb-2.5 rounded-[14px] border border-sky-100 bg-sky-50/70 px-3 py-2">
                              <div className="flex items-center gap-2">
                                <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
                                <p className="text-[12px] font-medium text-slate-800">
                                  {progressText}
                                </p>
                              </div>
                            </div>
                          ) : null}
                          <div className="space-y-2.5">
                            {executionGroups.map((group, index) => {
                              const completed = group.children.some(
                                (item) => item.kind === 'tool_completed',
                              );
                              return (
                                <details
                                  key={`${group.parent.created_at}-${group.parent.title}-${index}`}
                                  open={index === executionGroups.length - 1}
                                  className="group rounded-[14px] border border-slate-200 bg-slate-50/85"
                                >
                                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
                                    <div className="min-w-0">
                                      <div className="flex items-center gap-2">
                                        <span
                                          className={`h-2 w-2 rounded-full ${
                                            completed ? 'bg-emerald-500' : 'bg-sky-500'
                                          }`}
                                        />
                                        <p className="truncate text-[12px] font-medium text-slate-900">
                                          {group.parent.title}
                                        </p>
                                      </div>
                                      <p className="mt-1 break-words text-[11px] leading-4 text-slate-500">
                                        {group.parent.detail}
                                      </p>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                      <span className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
                                        {completed ? '已完成' : '进行中'}
                                      </span>
                                      <ChevronDown className="h-3.5 w-3.5 text-slate-400 transition group-open:rotate-180" />
                                    </div>
                                  </summary>
                                  <div className="border-t border-slate-200 px-3 py-2.5">
                                    <div className="space-y-2">
                                      {group.children.map((item, childIndex) => (
                                        <details
                                          key={`${item.created_at}-${item.kind}-${childIndex}`}
                                          open={item.kind === 'tool_completed' || childIndex === group.children.length - 1}
                                          className="group rounded-[12px] border border-slate-100 bg-white"
                                        >
                                          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2">
                                            <div className="min-w-0">
                                              <p className="truncate text-[11px] font-medium text-slate-700">
                                                {item.title}
                                              </p>
                                            </div>
                                            <div className="flex shrink-0 items-center gap-2">
                                              <span className="text-[10px] text-slate-400">
                                                {formatTimestamp(item.created_at)}
                                              </span>
                                              <ChevronDown className="h-3 w-3 text-slate-400 transition group-open:rotate-180" />
                                            </div>
                                          </summary>
                                          <div className="border-t border-slate-100 px-3 py-2">
                                            <p className="whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-600">
                                              {item.detail}
                                            </p>
                                          </div>
                                        </details>
                                      ))}
                                    </div>
                                  </div>
                                </details>
                              );
                            })}
                          </div>
                        </div>
                      </details>
                    </article>
                  ) : null}

                  <div className="h-px shrink-0" />
                </div>
              </div>

            </Panel>

            <form
              onSubmit={handleSubmit}
              className={`shrink-0 space-y-2.5 rounded-[22px] border border-white/80 bg-white/92 px-3.5 py-3 shadow-[0_16px_42px_rgba(15,23,42,0.10)] backdrop-blur-2xl ${mobilePane === 'workspace' ? 'hidden xl:block' : ''}`}
            >
                {composerMode === 'initial' ? (
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                    <label className="group inline-flex min-w-[220px] max-w-full cursor-pointer items-center gap-2 rounded-full border border-dashed border-slate-300 bg-white px-3 py-2 transition hover:border-sky-400 hover:bg-sky-50">
                      <Film className="h-3.5 w-3.5 text-sky-600" />
                      <span className="truncate text-[12px] text-slate-700">
                        {video ? video.name : '上传素材视频'}
                      </span>
                      <input
                        name="video"
                        type="file"
                        accept="video/*"
                        className="sr-only"
                        onChange={handleVideoChange}
                      />
                    </label>

                    <label
                      htmlFor="platform-main"
                      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2"
                    >
                      <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-slate-400">
                        平台
                      </span>
                      <select
                        id="platform-main"
                        value={platform}
                        onChange={(event) => setPlatform(event.target.value)}
                        className="bg-transparent text-[12px] font-medium text-slate-700 outline-none"
                      >
                        {PLATFORM_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <input
                      value={productManual}
                      onChange={(event) => setProductManual(event.target.value)}
                      className="min-w-[220px] flex-1 rounded-full border border-slate-200 bg-white px-3.5 py-2 text-[12px] text-slate-700 outline-none transition focus:border-sky-400"
                      placeholder="补充卖点、规格参数、品牌语气、禁用词…"
                    />
                  </div>
                ) : null}

                <div className="rounded-[18px] border border-slate-200 bg-slate-50 px-3 py-2.5 shadow-[0_10px_28px_rgba(15,23,42,0.06)]">
                  <div className="flex items-end gap-3">
                    <textarea
                      value={draftPrompt}
                      onChange={(event) => setDraftPrompt(event.target.value)}
                      rows={2}
                      disabled={isRunning || session?.status === 'awaiting_plan_selection'}
                      className="max-h-36 min-h-[44px] flex-1 resize-none bg-transparent px-1 py-1 text-[13px] leading-5 text-slate-800 outline-none placeholder:text-slate-400"
                      placeholder={
                        composerMode === 'initial'
                          ? '输入首轮创作要求，例如：25 秒 TikTok 版、前三秒强钩子、偏真人口播…'
                          : session?.status === 'awaiting_plan_selection'
                            ? '请先在右侧确认 Agent 执行计划。'
                          : '继续告诉助手要怎么改，例如：压缩到 20 秒、口语化一点、前三秒钩子更猛…'
                      }
                    />
                    <Button
                      type="submit"
                      size="icon"
                      aria-label="发送消息"
                      disabled={isRunning || !draftPreview || session?.status === 'awaiting_plan_selection'}
                      className="h-8 w-8 shrink-0 rounded-full"
                    >
                      <ArrowUp className="h-3 w-3" />
                    </Button>
                  </div>
                </div>

                {error ? (
                  <div
                    className="rounded-[16px] border border-rose-200 bg-rose-50 px-3 py-2.5 text-[12px] text-rose-700"
                    aria-live="polite"
                  >
                    {error}
                  </div>
                ) : null}
            </form>
          </section>

          <aside
            className={`min-h-0 overflow-hidden ${mobilePane === 'chat' ? 'hidden xl:block' : ''}`}
          >
            <Panel
              title=""
              className="h-full overflow-hidden"
              bodyClassName="flex min-h-0 flex-1 flex-col gap-2 p-0"
              hideHeader
            >
              <div className="flex h-full min-h-0 flex-col px-3.5 py-3">
                <div className="shrink-0 rounded-[18px] border border-slate-200 bg-slate-50/85 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm">
                        <Sparkles className="h-3.5 w-3.5" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-semibold text-slate-900">
                          {session ? activeSessionTitle : '执行工作区'}
                        </p>
                      </div>
                    </div>
                    <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">
                      {session?.status || 'idle'}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[11px] leading-4 text-slate-600" aria-live="polite">
                    {session
                      ? progressText
                      : '创建会话后，这里会先显示 Agent 计划，再展示已执行的分析结果与创意产物。'}
                  </p>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto pt-2 pr-1">
                {session && hasWorkspaceReply ? (
                  <div className="space-y-2.5">
                    {planOptions.length ? (
                      <WorkflowStepCard
                        title="Agent 执行计划"
                        status={
                          session.status === 'awaiting_plan_selection'
                            ? 'active'
                            : session.selected_plan_ids.length
                              ? 'completed'
                              : 'pending'
                        }
                        defaultOpen
                      >
                        <div className="space-y-3">
                          <div className="space-y-2.5">
                            {planOptions.map((option) => (
                              <label
                                key={option.id}
                                className={`flex cursor-pointer items-start gap-2.5 rounded-[16px] border px-2.5 py-2.5 ${
                                  selectedPlanIds.includes(option.id)
                                    ? 'border-sky-300 bg-sky-50'
                                    : 'border-slate-200 bg-white'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  className="mt-0.5 h-4 w-4 accent-sky-600"
                                  checked={selectedPlanIds.includes(option.id)}
                                  disabled={option.required || session.status !== 'awaiting_plan_selection'}
                                  onChange={() => togglePlanOption(option)}
                                />
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-[13px] font-medium text-slate-900">
                                      {option.title}
                                    </span>
                                    {option.required ? (
                                      <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[9px] uppercase tracking-[0.18em] text-white">
                                        必选
                                      </span>
                                    ) : null}
                                  </div>
                                  <p className="mt-1 text-[12px] leading-5 text-slate-600">
                                    {option.description}
                                  </p>
                                </div>
                              </label>
                            ))}
                          </div>
                        </div>
                      </WorkflowStepCard>
                    ) : null}

                    {currentExecutionGroup ? (
                      <WorkflowStepCard
                        title="当前步骤"
                        status={isRunning ? 'active' : 'completed'}
                        defaultOpen
                      >
                        <div className="space-y-2">
                          <div className="rounded-[16px] border border-slate-200 bg-white px-3 py-2.5">
                            <p className="text-[13px] font-medium text-slate-900">
                              {currentExecutionGroup.parent.title}
                            </p>
                            <p className="mt-1.5 text-[12px] leading-5 text-slate-600">
                              {currentExecutionGroup.parent.detail}
                            </p>
                          </div>
                          {currentExecutionGroup.children.length ? (
                            <div className="space-y-2">
                              {currentExecutionGroup.children.slice(-3).map((item, index) => (
                                <div
                                  key={`${item.created_at}-${index}`}
                                  className="rounded-[14px] border border-slate-100 bg-slate-50 px-3 py-2"
                                >
                                  <p className="text-[11px] font-medium text-slate-700">
                                    {item.title}
                                  </p>
                                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
                                    {item.detail}
                                  </p>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </WorkflowStepCard>
                    ) : null}

                    <WorkflowStepCard
                      title="当前产物概览"
                      status={session.status === 'completed' ? 'completed' : 'active'}
                      defaultOpen
                    >
                      <div className="space-y-2 text-[12px] leading-5 text-slate-600">
                        <div className="rounded-[14px] border border-slate-100 bg-white px-3 py-2">
                          关键帧：{session.keyframes.length} 张
                        </div>
                        <div className="rounded-[14px] border border-slate-100 bg-white px-3 py-2">
                          关键帧理解：{session.frame_analyses.length} 条
                        </div>
                        <div className="rounded-[14px] border border-slate-100 bg-white px-3 py-2">
                          视频摘要：{session.video_summary ? '已生成' : '未生成'}
                        </div>
                        <div className="rounded-[14px] border border-slate-100 bg-white px-3 py-2">
                          字幕草稿：{session.subtitle_draft ? '已生成' : '未生成'}
                        </div>
                        <div className="rounded-[14px] border border-slate-100 bg-white px-3 py-2">
                          剪辑方案：{session.editing_plan ? '已生成' : '未生成'}
                        </div>
                        <div className="rounded-[14px] border border-slate-100 bg-white px-3 py-2">
                          英文标题：{session.english_title ? '已生成' : '未生成'}
                        </div>
                        <div className="rounded-[14px] border border-slate-100 bg-white px-3 py-2">
                          标签：{session.tags.length ? `${session.tags.length} 个` : '未生成'}
                        </div>
                      </div>
                    </WorkflowStepCard>

                    {session.subtitle_draft ? (
                      <ArtifactCard title="字幕草稿" content={session.subtitle_draft} />
                    ) : null}

                    {session.editing_plan ? (
                      <ArtifactCard title="剪辑方案" content={session.editing_plan} />
                    ) : null}

                    {session.video_summary ? (
                      <ArtifactCard
                        title="视频摘要"
                        content={session.video_summary}
                        defaultOpen={false}
                      />
                    ) : null}

                    {session.english_title ? (
                      <ArtifactCard
                        title="英文标题"
                        content={session.english_title}
                        defaultOpen={false}
                      />
                    ) : null}

                    {session.tags.length ? (
                      <ArtifactCard
                        title="标签"
                        content={session.tags.map((tag) => `- ${tag}`).join('\n')}
                        defaultOpen={false}
                      />
                    ) : null}
                  </div>
                ) : (
                  <div className="rounded-[18px] border border-dashed border-slate-200 bg-white px-4 py-5 text-[13px] leading-5 text-slate-500">
                    Agent 的计划、关键帧结果和创意产物会在这里累计展开。
                  </div>
                )}
                </div>

                {session?.status === 'awaiting_plan_selection' ? (
                  <div className="shrink-0 pt-2">
                    <div className="rounded-[16px] border border-slate-200 bg-white/95 p-2.5 backdrop-blur">
                      <Button
                        type="button"
                        onClick={handleConfirmPlan}
                        disabled={isRunning}
                        className="h-9 w-full text-[13px]"
                      >
                        开始执行所选项
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            </Panel>
          </aside>
        </div>
      </div>

      {selectedKeyframe ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
          onClick={() => setSelectedKeyframe(null)}
        >
          <div
            className="max-h-[90vh] max-w-4xl overflow-hidden rounded-[28px] border border-white/20 bg-white shadow-[0_30px_100px_rgba(15,23,42,0.35)]"
            onClick={(event) => event.stopPropagation()}
          >
            <img
              src={`data:image/jpeg;base64,${selectedKeyframe.image_base64}`}
              alt="关键帧预览"
              className="max-h-[78vh] w-full object-contain bg-slate-950"
            />
            <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 text-sm text-slate-600">
              <div>
                预览图 · {formatSeconds(selectedKeyframe.timestamp_seconds)} ·{' '}
                {selectedKeyframe.source}
              </div>
              <button
                type="button"
                onClick={() => setSelectedKeyframe(null)}
                className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default CaptionGenerator;
