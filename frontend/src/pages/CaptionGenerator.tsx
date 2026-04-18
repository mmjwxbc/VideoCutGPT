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
  continueCaptionAssistantSession,
  createCaptionAssistantSession,
  getCaptionAssistantSession,
} from '../api/api';
import { CaptionAssistantSession, ChatMessage, Keyframe } from '../types';

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
  'completed',
  'error',
]);

const panelClassName =
  'rounded-[24px] border border-white/70 bg-white/78 shadow-[0_18px_50px_rgba(15,23,42,0.08)] backdrop-blur-xl';

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

const Panel: React.FC<PanelProps> = ({
  title,
  eyebrow,
  children,
  className = '',
  bodyClassName = '',
  hideHeader = false,
}) => (
  <section className={`${panelClassName} ${className}`}>
    {hideHeader ? null : (
      <div className="border-b border-slate-100 px-4 py-3">
        {eyebrow ? (
          <p className="text-[11px] font-medium uppercase tracking-[0.24em] text-slate-400">
            {eyebrow}
          </p>
        ) : null}
        <h2 className={`text-base font-semibold text-slate-900 ${eyebrow ? 'mt-2' : ''}`}>
          {title}
        </h2>
      </div>
    )}
    <div className={`px-4 py-3 ${bodyClassName}`}>{children}</div>
  </section>
);

const ChatBubble: React.FC<ChatBubbleProps> = ({ message }) => {
  const isAssistant = message.role === 'assistant';

  return (
    <article className={`flex gap-3 ${isAssistant ? 'justify-start' : 'justify-end'}`}>
      {isAssistant ? (
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#0f172a_0%,#2563eb_100%)] text-white shadow-md">
          <Bot className="h-4 w-4" />
        </div>
      ) : null}

      <div
        className={`w-full max-w-[min(100%,42rem)] rounded-[22px] px-4 py-3 shadow-[0_16px_42px_rgba(15,23,42,0.08)] ${isAssistant
            ? 'border border-white/70 bg-white text-slate-700'
            : 'bg-[linear-gradient(135deg,#111827_0%,#1d4ed8_100%)] text-white'
          }`}
      >
        <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.24em]">
          <span className={isAssistant ? 'text-slate-400' : 'text-white/60'}>
            {isAssistant ? 'Assistant' : 'You'}
          </span>
        </div>
        <p className="whitespace-pre-wrap break-words text-sm leading-7">
          {message.content}
        </p>
      </div>

      {!isAssistant ? (
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-700 shadow-sm">
          <User className="h-4 w-4" />
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
      className="group rounded-2xl border border-slate-200 bg-slate-50/80"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${statusClassName}`} />
          <h4 className="truncate text-sm font-medium text-slate-900">{title}</h4>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] uppercase tracking-[0.24em] text-slate-400">
            {statusLabel}
          </span>
          <ChevronDown className="h-4 w-4 text-slate-400 transition group-open:rotate-180" />
        </div>
      </summary>
      <div className="border-t border-slate-200 px-4 py-3 text-sm leading-6 text-slate-600">
        {children}
      </div>
    </details>
  );
};

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
  const [selectedKeyframe, setSelectedKeyframe] = useState<Keyframe | null>(null);
  const [sessionHistory, setSessionHistory] = useState<SessionListItem[]>([]);
  const [composerMode, setComposerMode] = useState<'initial' | 'followup'>(
    'initial',
  );
  const [mobilePane, setMobilePane] = useState<'chat' | 'workspace'>('chat');
  const threadRef = useRef<HTMLDivElement | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const messages = session?.messages ?? [];
  const draftPreview = useMemo(() => draftPrompt.trim(), [draftPrompt]);
  const progressText = session?.progress_message || '处理中…';
  const hasWorkspaceReply = Boolean(
    session?.keyframes?.length ||
    session?.video_summary ||
    session?.execution_plan?.length ||
    session?.subtitle_draft ||
    session?.editing_plan ||
    session?.english_title ||
    session?.tags?.length,
  );

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
    if (!threadRef.current || !threadEndRef.current) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      threadEndRef.current?.scrollIntoView({
        block: 'end',
        behavior: 'smooth',
      });
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [messages, loading, session?.progress_message]);

  useEffect(() => {
    if (!session?.session_id) {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      return;
    }

    eventSourceRef.current?.close();
    const source = new EventSource(captionSessionEventsUrl(session.session_id));
    eventSourceRef.current = source;

    const handleSnapshot = (raw: MessageEvent<string>) => {
      const nextSession = JSON.parse(raw.data) as CaptionAssistantSession;
      startTransition(() => {
        setSession(nextSession);
        setComposerMode('followup');
        setLoading(
          nextSession.status === 'queued' || nextSession.status === 'processing',
        );
        setError(
          nextSession.status === 'error'
            ? nextSession.error_message || '处理失败，请重试'
            : '',
        );
        upsertSessionHistory(nextSession);
      });
    };

    const handleProgress = (raw: MessageEvent<string>) => {
      const payload = JSON.parse(raw.data) as {
        session_id: string;
        status: CaptionAssistantSession['status'];
        message: string;
        updated_at: string;
      };
      setLoading(true);
      setSession((current) =>
        current
          ? {
            ...current,
            status: payload.status,
            progress_message: payload.message,
            updated_at: payload.updated_at,
          }
          : current,
      );
    };

    for (const eventName of SNAPSHOT_EVENTS) {
      source.addEventListener(eventName, handleSnapshot as EventListener);
    }
    source.addEventListener('progress', handleProgress as EventListener);
    source.onerror = () => {
      console.error('Caption SSE connection interrupted.');
    };

    return () => {
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
    };
  }, [session?.session_id]);

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
    setLoading(false);
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

    if (!session || !draftPreview) {
      return;
    }

    setLoading(true);
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

  const workflowSteps = session
    ? [
      {
        title: '1. 会话初始化',
        status: 'completed' as const,
        content: `会话已创建，平台为 ${session.platform}。`,
      },
      {
        title: '2. 关键帧提取',
        status: session.keyframes.length
          ? ('completed' as const)
          : session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.keyframes.length
          ? `已提取 ${session.keyframes.length} 张关键帧。`
          : '等待关键帧提取完成。',
      },
      {
        title: '3. 关键帧分析',
        status: session.frame_analyses.length
          ? ('completed' as const)
          : session.keyframes.length && session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.frame_analyses.length
          ? `${session.frame_analyses.length} 条分析结果已生成。`
          : '等待模型分析关键帧内容。',
      },
      {
        title: '4. 视频摘要',
        status: session.video_summary
          ? ('completed' as const)
          : session.frame_analyses.length && session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.video_summary || '等待视频摘要生成。',
      },
      {
        title: '5. 执行计划',
        status: session.execution_plan.length
          ? ('completed' as const)
          : session.video_summary && session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.execution_plan.length
          ? session.execution_plan.join('\n')
          : '等待本轮执行计划。',
      },
      {
        title: '6. 字幕草稿',
        status: session.subtitle_draft
          ? ('completed' as const)
          : session.execution_plan.length && session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.subtitle_draft || '等待字幕草稿生成。',
      },
      {
        title: '7. 剪辑方案',
        status: session.editing_plan
          ? ('completed' as const)
          : session.subtitle_draft && session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.editing_plan || '等待剪辑方案生成。',
      },
      {
        title: '8. 英文标题',
        status: session.english_title
          ? ('completed' as const)
          : session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.english_title || '等待英文标题生成。',
      },
      {
        title: '9. 标签',
        status: session.tags.length
          ? ('completed' as const)
          : session.status === 'processing'
            ? ('active' as const)
            : ('pending' as const),
        content: session.tags.length ? session.tags.join(', ') : '等待标签生成。',
      },
    ]
    : [];

  const activeSessionItem = sessionHistory.find(
    (item) => item.session_id === session?.session_id,
  );
  const activeSessionTitle =
    activeSessionItem?.title ||
    session?.messages.find((message) => message.role === 'user')?.content?.slice(0, 28) ||
    '未命名会话';

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[linear-gradient(180deg,#eef4ff_0%,#fbfdff_42%,#f6efe6_100%)] p-3 md:h-screen md:overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-8%] top-[-12%] h-72 w-72 rounded-full bg-sky-300/25 blur-3xl" />
        <div className="absolute right-[-6%] top-[12%] h-80 w-80 rounded-full bg-amber-300/20 blur-3xl" />
        <div className="absolute bottom-[-10%] left-[34%] h-72 w-72 rounded-full bg-emerald-200/20 blur-3xl" />
      </div>

      <div className="relative mx-auto flex min-h-[calc(100vh-1.5rem)] max-w-[1480px] flex-col overflow-hidden rounded-[30px] border border-white/60 bg-white/35 shadow-[0_32px_100px_rgba(15,23,42,0.12)] backdrop-blur-2xl md:h-[calc(100vh-1.5rem)]">
        <header className="flex shrink-0 items-center justify-between border-b border-white/50 px-5 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-3 text-xs font-medium uppercase tracking-[0.3em] text-slate-500">
              <Clapperboard className="h-4 w-4" />
              Caption Studio
            </div>
            <h1 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-slate-950">
              桌面工作台
            </h1>
          </div>

          <Link
            to="/"
            className="inline-flex h-10 items-center justify-center rounded-full border border-slate-200 bg-white/85 px-4 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-950"
          >
            返回首页
          </Link>
        </header>

        <div className="grid flex-1 gap-3 overflow-hidden p-3 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
          <aside className="min-h-0 overflow-hidden">
            <Panel
              title="历史会话"
              eyebrow="History"
              className="h-full overflow-hidden"
              bodyClassName="flex h-full min-h-0 flex-col"
            >
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
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-500">
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
                className={`inline-flex h-10 flex-1 items-center justify-center rounded-full border text-sm font-medium transition ${
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
                className={`inline-flex h-10 flex-1 items-center justify-center rounded-full border text-sm font-medium transition ${
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
              bodyClassName="flex h-full min-h-0 flex-col"
            >
              <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto pr-1">
                <div className="flex min-h-full flex-col justify-end gap-3 pb-6">
                  {!session ? (
                    <div className="flex min-h-[180px] items-center justify-center rounded-[22px] border border-slate-200 bg-slate-50/70 px-5 py-6 text-center">
                      <div className="max-w-lg">
                        <p className="text-[11px] font-medium uppercase tracking-[0.28em] text-slate-400">
                          Waiting For Session
                        </p>
                        <h3 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-slate-900">
                          先在下方创建你的第一轮任务
                        </h3>
                        <p className="mt-2 text-sm leading-6 text-slate-600">
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

                  {loading ? (
                    <div className="flex gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#0f172a_0%,#2563eb_100%)] text-white shadow-md">
                        <Bot className="h-4 w-4" />
                      </div>
                      <div
                        className="rounded-[22px] border border-white/70 bg-white px-4 py-3 shadow-[0_18px_50px_rgba(15,23,42,0.08)]"
                        aria-live="polite"
                      >
                        <div className="flex items-center gap-2">
                          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-slate-300" />
                          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-slate-400 [animation-delay:120ms]" />
                          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-slate-500 [animation-delay:240ms]" />
                        </div>
                        <p className="mt-3 text-sm leading-7 text-slate-600">
                          {progressText}
                        </p>
                      </div>
                    </div>
                  ) : null}

                  <div
                    ref={threadEndRef}
                    className="h-px shrink-0 scroll-mt-24 md:scroll-mt-32"
                  />
                </div>
              </div>
            </Panel>

            <Panel
              title={composerMode === 'initial' ? '开始新任务' : '继续改稿'}
              eyebrow="Composer"
              className={`sticky bottom-0 z-10 shrink-0 border-white/80 bg-white/88 shadow-[0_20px_60px_rgba(15,23,42,0.12)] backdrop-blur-2xl ${mobilePane === 'workspace' ? 'hidden xl:block' : ''}`}
              bodyClassName="space-y-2.5"
              hideHeader
            >
              <form
                onSubmit={handleSubmit}
                className="space-y-2.5 pb-[calc(env(safe-area-inset-bottom,0px)+0.25rem)]"
              >
                {composerMode === 'initial' ? (
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <label className="group inline-flex min-w-[220px] max-w-full cursor-pointer items-center gap-2 rounded-full border border-dashed border-slate-300 bg-white px-3 py-2 transition hover:border-sky-400 hover:bg-sky-50">
                      <Film className="h-4 w-4 text-sky-600" />
                      <span className="truncate text-sm text-slate-700">
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
                      <span className="text-[11px] font-medium uppercase tracking-[0.2em] text-slate-400">
                        平台
                      </span>
                      <select
                        id="platform-main"
                        value={platform}
                        onChange={(event) => setPlatform(event.target.value)}
                        className="bg-transparent text-sm font-medium text-slate-700 outline-none"
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
                      className="min-w-[240px] flex-1 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 outline-none transition focus:border-sky-400"
                      placeholder="补充卖点、规格参数、品牌语气、禁用词。"
                    />
                  </div>
                ) : null}

                <div className="rounded-[26px] border border-slate-200 bg-slate-50 px-3 py-3">
                  <div className="flex items-end gap-3">
                    <textarea
                      value={draftPrompt}
                      onChange={(event) => setDraftPrompt(event.target.value)}
                      rows={2}
                      disabled={loading}
                      className="min-h-[48px] flex-1 resize-none bg-transparent px-1 py-1 text-sm leading-6 text-slate-800 outline-none placeholder:text-slate-400"
                      placeholder={
                        composerMode === 'initial'
                          ? '输入首轮创作要求，例如：25 秒 TikTok 版、前三秒强钩子、偏真人口播。'
                          : '继续告诉助手要怎么改，例如：压缩到 20 秒、口语化一点、前三秒钩子更猛。'
                      }
                    />
                    <Button
                      type="submit"
                      size="icon"
                      disabled={loading || !draftPreview}
                      className="h-10 w-10 shrink-0 rounded-full"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {error ? (
                  <div
                    className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
                    aria-live="polite"
                  >
                    {error}
                  </div>
                ) : null}
              </form>
            </Panel>
          </section>

          <aside
            className={`min-h-0 overflow-hidden ${mobilePane === 'chat' ? 'hidden xl:block' : ''}`}
          >
            <Panel
              title="执行工作区"
              eyebrow="Workspace"
              className="h-full overflow-hidden"
              bodyClassName="flex h-full min-h-0 flex-col"
            >
              <div className="shrink-0 rounded-[22px] border border-slate-200 bg-slate-50/80 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.24em] text-slate-400">
                      <Sparkles className="h-4 w-4" />
                      Live Status
                    </div>
                    <h3 className="mt-1.5 text-sm font-semibold text-slate-900">
                      {session ? activeSessionTitle : '等待任务启动'}
                    </h3>
                  </div>
                  <span className="rounded-full bg-white px-3 py-1 text-[11px] font-medium uppercase tracking-[0.24em] text-slate-500">
                    {session?.status || 'idle'}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600" aria-live="polite">
                  {session
                    ? progressText
                    : '创建会话后，这里会按步骤展示关键帧提取、视频理解、字幕草稿与剪辑方案。'}
                </p>
              </div>

              <div className="mt-2 min-h-0 flex-1 overflow-y-auto pr-1">
                {session && hasWorkspaceReply ? (
                  <div className="space-y-3">
                    {workflowSteps.map((step) => (
                      <WorkflowStepCard
                        key={step.title}
                        title={step.title}
                        status={step.status}
                        defaultOpen={step.status === 'active' || step.status === 'completed'}
                      >
                        {step.title === '2. 关键帧提取' && session.keyframes.length ? (
                          <div className="space-y-3">
                            <p>{step.content}</p>
                            <div
                              onClick={(event) => {
                                const target = event.target as HTMLElement;
                                const button = target.closest('[data-keyframe-index]');
                                if (!button) {
                                  return;
                                }
                                const index = Number(
                                  button.getAttribute('data-keyframe-index'),
                                );
                                const keyframe = session.keyframes[index];
                                if (keyframe) {
                                  setSelectedKeyframe(keyframe);
                                }
                              }}
                            >
                              <div className="grid grid-cols-2 gap-2 2xl:grid-cols-3">
                                {session.keyframes.map((keyframe, index) => (
                                  <button
                                    key={`${keyframe.timestamp_seconds}-${index}`}
                                    type="button"
                                    data-keyframe-index={index}
                                    className="overflow-hidden rounded-2xl border border-slate-200 bg-white text-left transition hover:border-sky-300"
                                  >
                                    <img
                                      src={`data:image/jpeg;base64,${keyframe.image_base64}`}
                                      alt={`关键帧 ${index + 1}`}
                                      className="aspect-video w-full object-cover"
                                    />
                                    <div className="px-2 py-2 text-[11px] leading-5 text-slate-600">
                                      {index + 1} · {formatSeconds(keyframe.timestamp_seconds)}
                                    </div>
                                  </button>
                                ))}
                              </div>
                            </div>
                          </div>
                        ) : (
                          <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-slate-600">
                            {step.content}
                          </pre>
                        )}
                      </WorkflowStepCard>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-[22px] border border-dashed border-slate-200 bg-white px-4 py-5 text-sm leading-6 text-slate-500">
                    执行结果会在这里累计展开。你可以把这里当成只读工作台，专门看模型当前做到哪一步。
                  </div>
                )}
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
