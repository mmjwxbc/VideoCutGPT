import React, {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Link } from 'react-router-dom';
import {
  Bot,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  RefreshCcw,
  Sparkles,
  User,
} from 'lucide-react';

import { Button } from '../components/ui/button';
import ChatComposer from '../components/ChatComposer';
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
  EditingWorkflowState,
  ExecutionEventItem,
  ExecutionPlanOption,
  Keyframe,
  WorkflowArtifactState,
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

const panelClassName = 'border border-slate-800 bg-[#111111]';

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

interface AssistantTurnCardProps {
  message: ChatMessage;
  status: CaptionAssistantSession['status'] | undefined;
  isRunning: boolean;
  progressText: string;
  plannerStream: string;
  executionGroups: ExecutionGroup[];
  artifactSections: AssistantArtifactSection[];
}

interface AssistantArtifactSection {
  title: string;
  content: string;
  defaultOpen?: boolean;
}

interface WorkflowStateRow {
  key: string;
  item: WorkflowArtifactState;
}

const buildSessionHistoryItem = (
  nextSession: CaptionAssistantSession,
  fallbackTitle?: string,
  previousItem?: SessionListItem,
): SessionListItem => {
  const titleSource =
    previousItem?.title ||
    fallbackTitle ||
    nextSession.messages.find((message) => message.role === 'user')?.content ||
    '未命名会话';
  const subtitleSource =
    previousItem?.subtitle ||
    nextSession.video_summary ||
    nextSession.messages[nextSession.messages.length - 1]?.content ||
    nextSession.progress_message ||
    '等待处理';

  return {
    session_id: nextSession.session_id,
    title: titleSource.trim().slice(0, 28) || '未命名会话',
    subtitle: subtitleSource.trim().slice(0, 42) || '等待处理',
    updated_at: nextSession.updated_at,
  };
};

const buildAssistantArtifactSections = (
  nextSession: CaptionAssistantSession | null,
): AssistantArtifactSection[] => {
  if (!nextSession) {
    return [];
  }

  const sections: AssistantArtifactSection[] = [];
  if (nextSession.subtitle_draft.trim()) {
    sections.push({ title: '字幕草稿', content: nextSession.subtitle_draft.trim() });
  }
  if (nextSession.editing_plan.trim()) {
    sections.push({ title: '剪辑方案', content: nextSession.editing_plan.trim() });
  }
  if (nextSession.english_title.trim()) {
    sections.push({
      title: '英文标题',
      content: nextSession.english_title.trim(),
      defaultOpen: false,
    });
  }
  if (nextSession.tags.length) {
    sections.push({
      title: '标签',
      content: nextSession.tags.map((tag) => `- ${tag}`).join('\n'),
      defaultOpen: false,
    });
  }
  if (nextSession.video_summary.trim()) {
    sections.push({
      title: '视频摘要',
      content: nextSession.video_summary.trim(),
      defaultOpen: false,
    });
  }
  return sections;
};

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
      <div className="border-b border-slate-800 px-3.5 py-2.5">
        {eyebrow ? (
          <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-slate-500">
            {eyebrow}
          </p>
        ) : null}
        <h2 className={`text-[13px] font-semibold text-slate-100 ${eyebrow ? 'mt-1.5' : ''}`}>
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
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-100 shadow-sm">
          <Bot className="h-3 w-3" />
        </div>
      ) : null}

      <div
        className={`w-fit min-w-0 rounded-2xl px-3 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)] ${
          isAssistant
            ? 'max-w-[min(92%,52rem)] border border-slate-800 bg-[#161616] text-slate-200'
            : 'max-w-[min(72%,34rem)] bg-[#2a2a2a] text-white'
          }`}
      >
        <div className="mb-1 flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
          <span className={isAssistant ? 'text-slate-500' : 'text-white/60'}>
            {isAssistant ? 'Assistant' : 'You'}
          </span>
        </div>
        <p className="whitespace-pre-wrap break-words text-[12px] leading-5">
          {message.content}
        </p>
      </div>

      {!isAssistant ? (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-300 shadow-sm">
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
      className="group rounded-[18px] border border-slate-800 bg-[#171717]"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2.5 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${statusClassName}`} />
          <h4 className="truncate text-[13px] font-medium text-slate-100">{title}</h4>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="text-[10px] uppercase tracking-[0.22em] text-slate-500">
            {statusLabel}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-slate-500 transition group-open:rotate-180" />
        </div>
      </summary>
      <div className="border-t border-slate-800 px-3 py-2.5 text-[13px] leading-5 text-slate-400">
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
    className="group rounded-[18px] border border-slate-800 bg-[#141414]"
  >
    <summary className="flex cursor-pointer list-none items-center justify-between gap-2.5 px-3 py-2.5">
      <h4 className="truncate text-[13px] font-medium text-slate-100">{title}</h4>
      <ChevronDown className="h-3.5 w-3.5 text-slate-500 transition group-open:rotate-180" />
    </summary>
    <div className="border-t border-slate-800 px-3 py-2.5">
      <pre className="whitespace-pre-wrap break-words font-sans text-[12px] leading-5 text-slate-300">
        {content}
      </pre>
    </div>
  </details>
);

const AssistantTurnCard: React.FC<AssistantTurnCardProps> = ({
  message,
  status,
  isRunning,
  progressText,
  plannerStream,
  executionGroups,
  artifactSections,
}) => (
  <article className="flex w-full items-start gap-2.5 justify-start pr-3 sm:pr-8">
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-100 shadow-sm">
      <Bot className="h-3 w-3" />
    </div>

    <div className="w-full max-w-[min(92%,52rem)] rounded-2xl border border-slate-800 bg-[#161616] px-3 py-2.5 text-slate-300 shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
      <div className="mb-1 flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
        <span className="text-slate-500">Assistant</span>
      </div>

      {plannerStream.trim() || executionGroups.length || isRunning ? (
        <div className="mb-3 space-y-2.5 border-b border-slate-800 pb-3">
          <div className="rounded-[14px] border border-slate-800 bg-[#1b1b1b] px-3 py-2.5">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[12px] font-medium text-slate-100">思考过程</p>
                <p className="mt-1 text-[11px] leading-4 text-slate-400">
                  {status === 'awaiting_plan_selection'
                    ? '计划已生成，等待你确认后执行'
                    : isRunning
                      ? progressText
                      : `${executionGroups.length} 个工具步骤`}
                </p>
              </div>
              <span className="shrink-0 text-[10px] uppercase tracking-[0.18em] text-slate-500">
                {status === 'awaiting_plan_selection'
                  ? '待确认'
                  : isRunning
                    ? '进行中'
                    : '已完成'}
              </span>
            </div>
          </div>

          {plannerStream.trim() ? (
            <div className="rounded-[14px] border border-slate-800 bg-[#1b1b1b] px-3 py-2.5">
              <p className="mb-1 text-[11px] font-medium text-slate-300">Agent 规划输出</p>
              <p className="whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-400">
                {plannerStream}
              </p>
            </div>
          ) : null}

          {executionGroups.map((group, index) => {
            const completed = group.children.some((item) => item.kind === 'tool_completed');
            return (
              <details
                key={`${group.parent.created_at}-${group.parent.title}-${index}`}
                open={index === executionGroups.length - 1}
                className="group rounded-[14px] border border-slate-800 bg-[#1b1b1b]"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          completed ? 'bg-emerald-500' : 'bg-sky-500'
                        }`}
                      />
                      <p className="truncate text-[12px] font-medium text-slate-100">
                        {group.parent.title}
                      </p>
                    </div>
                    <p className="mt-1 break-words text-[11px] leading-4 text-slate-400">
                      {group.parent.detail}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                      {completed ? '已完成' : '进行中'}
                    </span>
                    <ChevronDown className="h-3.5 w-3.5 text-slate-500 transition group-open:rotate-180" />
                  </div>
                </summary>
                <div className="border-t border-slate-800 px-3 py-2.5">
                  <div className="space-y-2">
                    {group.children.map((item, childIndex) => (
                      <details
                        key={`${item.created_at}-${item.kind}-${childIndex}`}
                        open={item.kind === 'tool_completed' || childIndex === group.children.length - 1}
                        className="group rounded-[12px] border border-slate-800 bg-[#121212]"
                      >
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2">
                          <div className="min-w-0">
                            <p className="truncate text-[11px] font-medium text-slate-200">
                              {item.title}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <span className="text-[10px] text-slate-500">
                              {formatTimestamp(item.created_at)}
                            </span>
                            <ChevronDown className="h-3 w-3 text-slate-500 transition group-open:rotate-180" />
                          </div>
                        </summary>
                        <div className="border-t border-slate-800 px-3 py-2">
                          <p className="whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-400">
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
      ) : null}

      <p className="whitespace-pre-wrap break-words text-[12px] leading-5">
        {message.content}
      </p>

      {artifactSections.length ? (
        <div className="mt-3 space-y-2.5 border-t border-slate-800 pt-3">
          {artifactSections.map((section) => (
            <ArtifactCard
              key={section.title}
              title={section.title}
              content={section.content}
              defaultOpen={section.defaultOpen ?? true}
            />
          ))}
        </div>
      ) : null}
    </div>
  </article>
);

const getWorkflowRows = (
  workflowState: EditingWorkflowState | null | undefined,
): WorkflowStateRow[] => {
  if (!workflowState) {
    return [];
  }
  return [
    { key: 'keyframe_analysis', item: workflowState.keyframe_analysis },
    { key: 'video_summary', item: workflowState.video_summary },
    { key: 'subtitle_draft', item: workflowState.subtitle_draft },
    { key: 'editing_plan', item: workflowState.editing_plan },
    { key: 'english_title', item: workflowState.english_title },
    { key: 'tags', item: workflowState.tags },
  ];
};

const getWorkflowStatusTone = (status: string) => {
  switch (status) {
    case 'completed':
      return 'bg-emerald-500';
    case 'in_progress':
      return 'bg-sky-500';
    case 'planned':
      return 'bg-amber-400';
    case 'error':
      return 'bg-rose-500';
    default:
      return 'bg-slate-300';
  }
};

const getWorkflowStatusLabel = (status: string) => {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'in_progress':
      return '进行中';
    case 'planned':
      return '待确认';
    case 'error':
      return '异常';
    default:
      return '未执行';
  }
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
  const [selectedKeyframe, setSelectedKeyframe] = useState<Keyframe | null>(null);
  const [sessionHistory, setSessionHistory] = useState<SessionListItem[]>([]);
  const [composerMode, setComposerMode] = useState<'initial' | 'followup'>(
    'initial',
  );
  const [mobilePane, setMobilePane] = useState<'chat' | 'workspace'>('chat');
  const [selectedPlanIds, setSelectedPlanIds] = useState<string[]>([]);
  const [historySidebarCollapsed, setHistorySidebarCollapsed] = useState<boolean>(false);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

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
  const workflowRows = useMemo(
    () => getWorkflowRows(session?.editing_state),
    [session?.editing_state],
  );
  const assistantArtifactSections = useMemo(
    () => buildAssistantArtifactSections(session),
    [session],
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
  const showExecutionReplyInChat = Boolean(
    session &&
      (isRunning ||
        session.status === 'awaiting_plan_selection' ||
        session.planner_stream.trim() ||
        executionGroups.length),
  );
  const hasWorkspaceReply = Boolean(
    session?.plan_options?.length ||
    session?.execution_events?.length ||
    session?.agent_trace?.length ||
    session?.execution_plan?.length ||
    workflowRows.length,
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
      if (nextSession.status === 'completed' || nextSession.status === 'error') {
        closeSource();
        void reconcileTerminalSession(nextSession.session_id);
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
      if (payload.status === 'completed' || payload.status === 'error') {
        closeSource();
        void reconcileTerminalSession(payload.session_id);
      }
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
        updated_at: string;
      };
      setSession((current) => {
        if (!current) {
          return current;
        }
        if (isOlderTimestamp(payload.updated_at, current.updated_at)) {
          return current;
        }
        return {
          ...current,
          planner_stream: payload.content,
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

        startTransition(() => {
          setSession(response);
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

    try {
      const response = await continueCaptionAssistantSession(
        session.session_id,
        normalizedPrompt,
      );

      startTransition(() => {
        setSession(response);
        setDraftPrompt('');
        setMobilePane('chat');
      });
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
          <aside className="hidden min-h-0 overflow-hidden bg-[#0f0f0f] lg:block">
            <Panel
              title=""
              className="h-full overflow-hidden border-0 bg-[#0f0f0f]"
              bodyClassName="flex min-h-0 flex-1 flex-col"
              hideHeader
            >
              {historySidebarCollapsed ? (
                <>
                  <div className="flex shrink-0 flex-col items-center">
                    <button
                      type="button"
                      onClick={() => setHistorySidebarCollapsed(false)}
                      className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-800 bg-[#171717] text-slate-300 transition hover:border-slate-700 hover:bg-[#1b1b1b] hover:text-white"
                      aria-label="展开历史侧栏"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="mb-3 flex shrink-0 items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">
                        <Clapperboard className="h-3 w-3" />
                        Caption Studio
                      </div>
                      <h1 className="mt-1 text-[17px] font-semibold text-slate-100">
                        桌面工作台
                      </h1>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setHistorySidebarCollapsed(true)}
                        className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-800 bg-[#171717] text-slate-300 transition hover:border-slate-700 hover:bg-[#1b1b1b] hover:text-white"
                        aria-label="收起历史侧栏"
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </button>
                      <Link
                        to="/"
                        className="shrink-0 rounded-full border border-slate-800 bg-[#171717] px-2.5 py-1.5 text-[11px] font-medium text-slate-300 transition hover:border-slate-700 hover:text-white"
                      >
                        返回
                      </Link>
                    </div>
                  </div>

                  <Button
                    type="button"
                    variant="outline"
                    className="mb-3 w-full border-slate-800 bg-[#171717] text-slate-200 hover:border-slate-700 hover:bg-[#1b1b1b] hover:text-white"
                    onClick={resetSession}
                  >
                    <RefreshCcw className="mr-2 h-4 w-4" />
                    新建任务
                  </Button>

                  <div className="min-h-0 flex-1 overflow-y-auto pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    <div className="space-y-2">
                      {sessionHistory.length ? (
                        sessionHistory.map((item) => {
                          const isActive = session?.session_id === item.session_id;
                          return (
                            <button
                              key={item.session_id}
                              type="button"
                              onClick={() => void openSessionFromHistory(item.session_id)}
                              className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                                isActive
                                  ? 'border-sky-500/40 bg-sky-500/10 shadow-sm'
                                  : 'border-slate-800 bg-[#171717] hover:border-slate-700 hover:bg-[#1b1b1b]'
                              }`}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <p className="truncate text-sm font-medium text-slate-100">
                                  {item.title}
                                </p>
                                <span className="shrink-0 text-[11px] text-slate-500">
                                  {formatTimestamp(item.updated_at)}
                                </span>
                              </div>
                              <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">
                                {item.subtitle}
                              </p>
                            </button>
                          );
                        })
                      ) : (
                        <div className="rounded-[18px] border border-dashed border-slate-800 bg-[#151515] px-3.5 py-4 text-[13px] leading-5 text-slate-400">
                          还没有历史会话。创建首轮任务后，后续所有版本都会沉淀在这里。
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </Panel>
          </aside>

          <section className="flex min-h-0 flex-col overflow-hidden bg-[#090909]">
            <div className="flex items-center gap-2 border-b border-slate-800 bg-[#0f0f0f] px-4 py-3 lg:hidden">
              <button
                type="button"
                onClick={() => setMobilePane('chat')}
                className={`inline-flex h-8 flex-1 items-center justify-center rounded-full border text-[12px] font-medium transition ${
                  mobilePane === 'chat'
                    ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
                    : 'border-slate-800 bg-[#171717] text-slate-400'
                }`}
              >
                聊天记录
              </button>
              <button
                type="button"
                onClick={() => setMobilePane('workspace')}
                className={`inline-flex h-8 flex-1 items-center justify-center rounded-full border text-[12px] font-medium transition ${
                  mobilePane === 'workspace'
                    ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
                    : 'border-slate-800 bg-[#171717] text-slate-400'
                }`}
              >
                执行工作区
              </button>
            </div>

            <div
              className={`flex min-h-0 flex-1 flex-col ${mobilePane === 'workspace' ? 'hidden lg:flex' : ''}`}
            >
              <div
                ref={threadRef}
                className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#090909] px-6 py-5 [overflow-anchor:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              >
                <div className="flex min-h-full flex-col gap-3 pb-6">
                  {!session ? (
                    <div className="flex min-h-[160px] items-center justify-center rounded-[18px] border border-slate-800 bg-[#141414] px-3.5 py-4 text-center">
                      <div className="max-w-lg">
                        <p className="text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">
                          Waiting For Session
                        </p>
                        <h3 className="mt-2 text-[15px] font-semibold tracking-[-0.04em] text-slate-100">
                          先在下方创建你的第一轮任务
                        </h3>
                        <p className="mt-2 text-[12px] leading-5 text-slate-400">
                          提交后，这里会持续显示用户要求、助手回复和后续每一轮改稿指令。
                        </p>
                      </div>
                    </div>
                  ) : (
                    messages.map((message, index) => (
                      <div key={`${message.created_at}-${index}`} className="space-y-2.5">
                        {message.role === 'assistant' && index === messages.length - 1 ? (
                          <AssistantTurnCard
                            message={message}
                            status={session?.status}
                            isRunning={isRunning}
                            progressText={progressText}
                            plannerStream={session?.planner_stream ?? ''}
                            executionGroups={executionGroups}
                            artifactSections={assistantArtifactSections}
                          />
                        ) : (
                          <ChatBubble message={message} />
                        )}
                      </div>
                    ))
                  )}

                  {showExecutionReplyInChat && messages[messages.length - 1]?.role !== 'assistant' ? (
                    <article className="flex w-full items-start gap-2.5 justify-start pr-16">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-100 shadow-sm">
                        <Bot className="h-3 w-3" />
                      </div>
                      <details
                        open
                        className="group w-fit min-w-0 max-w-[min(72%,34rem)] rounded-2xl border border-slate-800 bg-[#161616] text-slate-300 shadow-[0_10px_24px_rgba(0,0,0,0.18)]"
                      >
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span
                                className={`h-2 w-2 rounded-full ${
                                  isRunning ? 'bg-sky-500' : 'bg-emerald-500'
                                }`}
                              />
                              <p className="truncate text-[12px] font-medium text-slate-100">
                                Assistant 执行回复
                              </p>
                            </div>
                            <p className="mt-1 break-words text-[11px] leading-4 text-slate-400">
                              {session?.status === 'awaiting_plan_selection'
                                ? '计划已生成，等待你确认后执行'
                                : isRunning
                                  ? progressText
                                  : `${executionGroups.length} 个工具步骤，点击展开查看完整执行树`}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                              {session?.status === 'awaiting_plan_selection'
                                ? '待确认'
                                : isRunning
                                  ? '进行中'
                                  : '已完成'}
                            </span>
                            <ChevronDown className="h-3.5 w-3.5 text-slate-500 transition group-open:rotate-180" />
                          </div>
                        </summary>
                        <div className="border-t border-slate-800 px-3 py-2.5">
                          {session?.planner_stream?.trim() ? (
                            <div className="mb-2.5 rounded-[14px] border border-slate-800 bg-[#1b1b1b] px-3 py-2.5">
                              <p className="mb-1 text-[11px] font-medium text-slate-300">
                                Agent 规划输出
                              </p>
                              <p className="whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-400">
                                {session.planner_stream}
                              </p>
                            </div>
                          ) : null}
                          {isRunning ? (
                            <div className="mb-2.5 rounded-[14px] border border-sky-500/20 bg-sky-500/10 px-3 py-2">
                              <div className="flex items-center gap-2">
                                <span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />
                                <p className="text-[12px] font-medium text-slate-100">
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
                                  className="group rounded-[14px] border border-slate-800 bg-[#1b1b1b]"
                                >
                                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
                                    <div className="min-w-0">
                                      <div className="flex items-center gap-2">
                                        <span
                                          className={`h-2 w-2 rounded-full ${
                                            completed ? 'bg-emerald-500' : 'bg-sky-500'
                                          }`}
                                        />
                                        <p className="truncate text-[12px] font-medium text-slate-100">
                                          {group.parent.title}
                                        </p>
                                      </div>
                                      <p className="mt-1 break-words text-[11px] leading-4 text-slate-400">
                                        {group.parent.detail}
                                      </p>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                      <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                                        {completed ? '已完成' : '进行中'}
                                      </span>
                                      <ChevronDown className="h-3.5 w-3.5 text-slate-500 transition group-open:rotate-180" />
                                    </div>
                                  </summary>
                                  <div className="border-t border-slate-800 px-3 py-2.5">
                                    <div className="space-y-2">
                                      {group.children.map((item, childIndex) => (
                                        <details
                                          key={`${item.created_at}-${item.kind}-${childIndex}`}
                                          open={item.kind === 'tool_completed' || childIndex === group.children.length - 1}
                                          className="group rounded-[12px] border border-slate-800 bg-[#121212]"
                                        >
                                          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2">
                                            <div className="min-w-0">
                                              <p className="truncate text-[11px] font-medium text-slate-200">
                                                {item.title}
                                              </p>
                                            </div>
                                            <div className="flex shrink-0 items-center gap-2">
                                              <span className="text-[10px] text-slate-500">
                                                {formatTimestamp(item.created_at)}
                                              </span>
                                              <ChevronDown className="h-3 w-3 text-slate-500 transition group-open:rotate-180" />
                                            </div>
                                          </summary>
                                          <div className="border-t border-slate-800 px-3 py-2">
                                            <p className="whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-400">
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

              <div
                className={`shrink-0 bg-[#090909] px-6 pb-5 pt-4 ${mobilePane === 'workspace' ? 'hidden lg:block' : ''}`}
              >
              <ChatComposer
                className="mx-auto"
                value={draftPrompt}
                onChange={setDraftPrompt}
                onSubmit={(nextValue) => {
                  void submitPrompt(nextValue);
                }}
                disabled={isRunning || session?.status === 'awaiting_plan_selection'}
                platform={platform}
                platformOptions={PLATFORM_OPTIONS}
                onPlatformChange={setPlatform}
                onUploadClick={() => {
                  if (composerMode !== 'initial') {
                    return;
                  }
                  uploadInputRef.current?.click();
                }}
                uploadPreviewUrl={composerMode === 'initial' ? videoPreviewUrl : null}
                uploadPreviewName={composerMode === 'initial' ? video?.name ?? null : null}
                onClearUploadPreview={
                  composerMode === 'initial' ? clearUploadedVideo : undefined
                }
                sellingPointsValue={productManual}
                onSellingPointsChange={setProductManual}
                sellingPointsOpen={sellingPointsOpen}
                onSellingPointsToggle={() => setSellingPointsOpen((current) => !current)}
                toolsDisabled={composerMode !== 'initial' || isRunning}
                placeholder={
                  composerMode === 'initial'
                    ? '有问题，尽管问'
                    : session?.status === 'awaiting_plan_selection'
                      ? '请先在右侧确认 Agent 执行计划。'
                      : '有问题，尽管问'
                }
              />

              {error ? (
                <div
                  className="mx-auto mt-3 w-full max-w-[960px] rounded-2xl border border-rose-900/60 bg-rose-950/40 px-4 py-3 text-[12px] text-rose-200"
                  aria-live="polite"
                >
                  {error}
                </div>
              ) : null}
            </div>
            </div>
          </section>

          <aside
            className={`min-h-0 overflow-hidden bg-[#0f0f0f] ${mobilePane === 'chat' ? 'hidden lg:block' : ''}`}
          >
            <Panel
              title=""
              className="h-full overflow-hidden border-0 bg-[#0f0f0f]"
              bodyClassName="flex min-h-0 flex-1 flex-col gap-2 p-0"
              hideHeader
            >
              <div className="flex h-full min-h-0 flex-col px-3.5 py-3">
                <div className="shrink-0 rounded-[18px] border border-slate-800 bg-[#171717] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#111111] text-slate-300 shadow-sm">
                        <Sparkles className="h-3.5 w-3.5" />
                      </div>
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-semibold text-slate-100">
                          {session ? activeSessionTitle : '执行工作区'}
                        </p>
                      </div>
                    </div>
                    <span className="shrink-0 rounded-full border border-slate-700 bg-[#111111] px-2 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
                      {session?.status || 'idle'}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[11px] leading-4 text-slate-400" aria-live="polite">
                    {session
                      ? progressText
                      : '创建会话后，这里会先显示 Agent 计划，再展示已执行的分析结果与创意产物。'}
                  </p>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto pt-2 pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
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
                                    ? 'border-sky-500/40 bg-sky-500/10'
                                    : 'border-slate-800 bg-[#111111]'
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
                                    <span className="text-[13px] font-medium text-slate-100">
                                      {option.title}
                                    </span>
                                    {option.required ? (
                                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] uppercase tracking-[0.18em] text-black">
                                        必选
                                      </span>
                                    ) : null}
                                  </div>
                                  <p className="mt-1 text-[12px] leading-5 text-slate-400">
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
                          <div className="rounded-[16px] border border-slate-800 bg-[#111111] px-3 py-2.5">
                            <p className="text-[13px] font-medium text-slate-100">
                              {currentExecutionGroup.parent.title}
                            </p>
                            <p className="mt-1.5 text-[12px] leading-5 text-slate-400">
                              {currentExecutionGroup.parent.detail}
                            </p>
                          </div>
                          {currentExecutionGroup.children.length ? (
                            <div className="space-y-2">
                              {currentExecutionGroup.children.slice(-3).map((item, index) => (
                                <div
                                  key={`${item.created_at}-${index}`}
                                  className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2"
                                >
                                  <p className="text-[11px] font-medium text-slate-200">
                                    {item.title}
                                  </p>
                                  <p className="mt-1 text-[11px] leading-4 text-slate-400">
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
                      title="剪辑状态"
                      status={session.status === 'completed' ? 'completed' : 'active'}
                      defaultOpen
                    >
                      <div className="space-y-2 text-[12px] leading-5 text-slate-400">
                        <div className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                            Request
                          </div>
                          <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-slate-300">
                            {session.editing_state?.request_summary || '暂无'}
                          </p>
                        </div>
                        {workflowRows.map(({ key, item }) => (
                          <div
                            key={key}
                            className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex min-w-0 items-center gap-2">
                                <span
                                  className={`h-2 w-2 rounded-full ${getWorkflowStatusTone(item.status)}`}
                                />
                                <p className="truncate text-[12px] font-medium text-slate-200">
                                  {item.label}
                                </p>
                              </div>
                              <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                                {getWorkflowStatusLabel(item.status)}
                              </span>
                            </div>
                            <p className="mt-1 text-[11px] leading-4 text-slate-400">
                              {item.detail || '暂无状态说明'}
                            </p>
                            {item.needs_refresh ? (
                              <p className="mt-1 text-[11px] text-amber-600">
                                已标记为需要刷新
                              </p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </WorkflowStepCard>
                  </div>
                ) : (
                  <div className="rounded-[18px] border border-dashed border-slate-800 bg-[#151515] px-4 py-5 text-[13px] leading-5 text-slate-400">
                    Agent 的计划、步骤状态和执行进度会在这里持续更新。
                  </div>
                )}
                </div>

                {session?.status === 'awaiting_plan_selection' ? (
                  <div className="shrink-0 pt-2">
                    <div className="rounded-[16px] border border-slate-800 bg-[#171717]/95 p-2.5 backdrop-blur">
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
