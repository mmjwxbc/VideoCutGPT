import React from 'react';
import { Bot, ChevronDown, User, Wrench } from 'lucide-react';

import {
  AgentTurn,
  CaptionAssistantSession,
  CaptionAssistantSessionSummary,
  EditingWorkflowState,
  TurnEventItem,
  WorkflowArtifactState,
} from '../../types';

export interface SessionListItem {
  session_id: string;
  title: string;
  subtitle: string;
  status: 'idle' | 'processing' | 'completed' | 'error';
  updated_at: string;
}

export interface WorkflowStateRow {
  key: string;
  item: WorkflowArtifactState;
}

interface PanelProps {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  hideHeader?: boolean;
}

interface ChatBubbleProps {
  content: string;
}

interface WorkflowStepCardProps {
  title: string;
  status: 'pending' | 'active' | 'completed';
  children: React.ReactNode;
  defaultOpen?: boolean;
}

interface AssistantTurnCardProps {
  turn: AgentTurn;
  isActive: boolean;
}

const panelClassName = 'theme-transition border ws-card';

export const formatTimestamp = (value: string) =>
  new Date(value).toLocaleString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    month: 'numeric',
    day: 'numeric',
  });

export const buildSessionHistoryItem = (
  nextSession: CaptionAssistantSession,
  fallbackTitle?: string,
  previousItem?: SessionListItem,
): SessionListItem => {
  const firstTurn = nextSession.turns[0];
  const lastTurn = nextSession.turns[nextSession.turns.length - 1];
  const titleSource =
    previousItem?.title ||
    fallbackTitle ||
    firstTurn?.user_prompt ||
    nextSession.global_editing_state.request_summary ||
    '未命名会话';
  const subtitleSource =
    lastTurn?.final_text ||
    (lastTurn?.status === 'running' ? '当前轮次执行中' : '') ||
    previousItem?.subtitle ||
    '等待处理';

  return {
    session_id: nextSession.session_id,
    title: titleSource.trim().slice(0, 28) || '未命名会话',
    subtitle: subtitleSource.trim().slice(0, 42) || '等待处理',
    status: nextSession.status,
    updated_at: nextSession.updated_at,
  };
};

export const buildSessionHistoryItemFromSummary = (
  summary: CaptionAssistantSessionSummary,
): SessionListItem => ({
  session_id: summary.session_id,
  title: summary.title.trim().slice(0, 28) || '未命名会话',
  subtitle: summary.subtitle.trim().slice(0, 42) || '等待处理',
  status: summary.status,
  updated_at: summary.updated_at,
});

export const getWorkflowRows = (
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
    { key: 'edited_video', item: workflowState.edited_video },
  ];
};

export const getWorkflowStatusTone = (status: string) => {
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

export const getWorkflowStatusLabel = (status: string) => {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'in_progress':
      return '进行中';
    case 'planned':
      return '待执行';
    case 'error':
      return '异常';
    default:
      return '未执行';
  }
};

export const Panel: React.FC<PanelProps> = ({
  title,
  eyebrow,
  children,
  className = '',
  bodyClassName = '',
  hideHeader = false,
}) => (
  <section className={`${panelClassName} flex min-h-0 flex-col ${className}`}>
    {hideHeader ? null : (
      <div className="border-b border-ws px-3.5 py-2.5">
        {eyebrow ? (
          <p className="text-ws-soft text-[10px] font-medium uppercase tracking-[0.22em]">
            {eyebrow}
          </p>
        ) : null}
        <h2 className={`text-ws-primary text-[13px] font-semibold ${eyebrow ? 'mt-1.5' : ''}`}>
          {title}
        </h2>
      </div>
    )}
    <div className={`min-h-0 px-3.5 py-3 ${bodyClassName}`}>{children}</div>
  </section>
);

export const ChatBubble: React.FC<ChatBubbleProps> = ({ content }) => (
  <article className="flex w-full items-start gap-2.5 justify-end pl-10 sm:pl-24">
    <div className="theme-transition w-fit max-w-[min(72%,34rem)] min-w-0 rounded-2xl bg-[color:var(--workspace-text-primary)] px-3 py-2.5 text-[color:var(--workspace-shell)] shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
      <div className="mb-1 flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
        <span className="text-white/60">You</span>
      </div>
      <p className="whitespace-pre-wrap break-words text-[12px] leading-5">{content}</p>
    </div>
    <div className="theme-transition ws-icon text-ws-secondary flex h-7 w-7 shrink-0 items-center justify-center rounded-full border shadow-sm">
      <User className="h-3 w-3" />
    </div>
  </article>
);

export const WorkflowStepCard: React.FC<WorkflowStepCardProps> = ({
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
      className="theme-transition group rounded-[18px] border ws-card"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2.5 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${statusClassName}`} />
          <h4 className="text-ws-primary truncate text-[13px] font-medium">{title}</h4>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="text-ws-soft text-[10px] uppercase tracking-[0.22em]">
            {statusLabel}
          </span>
          <ChevronDown className="text-ws-soft h-3.5 w-3.5 transition group-open:rotate-180" />
        </div>
      </summary>
      <div className="text-ws-muted border-t border-ws px-3 py-2.5 text-[13px] leading-5">
        {children}
      </div>
    </details>
  );
};

const TurnEventDisclosure: React.FC<{
  title: string;
  timestamp: string;
  children: React.ReactNode;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
}> = ({
  title,
  timestamp,
  children,
  icon,
  defaultOpen = false,
}) => (
  <details
    open={defaultOpen}
    className="theme-transition group rounded-[14px] border ws-card-muted"
  >
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
      <div className="flex min-w-0 items-center gap-2">
        {icon}
        <p className="text-ws-primary truncate text-[12px] font-medium">{title}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="text-ws-soft text-[10px]">{formatTimestamp(timestamp)}</span>
        <ChevronDown className="text-ws-soft h-3.5 w-3.5 transition group-open:rotate-180" />
      </div>
    </summary>
    <div className="border-t border-ws px-3 py-2.5">
      {children}
    </div>
  </details>
);

const renderTurnEvent = (event: TurnEventItem, index: number, defaultOpen: boolean) => {
  if (event.type === 'tool_call') {
    return (
      <TurnEventDisclosure
        key={`${event.created_at}-${index}`}
        title={event.tool_name}
        timestamp={event.created_at}
        icon={<Wrench className="text-ws-muted h-3.5 w-3.5" />}
        defaultOpen={defaultOpen}
      >
        <pre className="theme-transition text-ws-muted whitespace-pre-wrap break-words rounded-[12px] border ws-card-contrast px-3 py-2 text-[11px] leading-5">
          {event.arguments || '{}'}
        </pre>
      </TurnEventDisclosure>
    );
  }

  if (event.type === 'thought') {
    return (
      <TurnEventDisclosure
        key={`${event.created_at}-${index}`}
        title="思考过程"
        timestamp={event.created_at}
        defaultOpen={defaultOpen}
      >
        <p className="text-ws-muted whitespace-pre-wrap break-words text-[12px] leading-5">
          {event.content}
        </p>
      </TurnEventDisclosure>
    );
  }

  return null;
};

export const AssistantTurnCard: React.FC<AssistantTurnCardProps> = ({
  turn,
  isActive,
}) => {
  const processEvents = turn.events.filter((event) => event.type !== 'final_text');
  const finalEvent = turn.events.find((event) => event.type === 'final_text');
  const latestEventIndex = processEvents.length - 1;

  return (
    <article className="flex w-full items-start gap-2.5 justify-start pr-3 sm:pr-8">
      <div className="theme-transition ws-icon text-ws-primary flex h-7 w-7 shrink-0 items-center justify-center rounded-full border shadow-sm">
        <Bot className="h-3 w-3" />
      </div>

      <div className="theme-transition text-ws-secondary w-full max-w-[min(92%,52rem)] rounded-2xl border ws-card px-3 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
        <div className="border-ws mb-3 flex items-center justify-between gap-3 border-b pb-3">
          <div className="flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
            <span className="text-ws-soft">Assistant</span>
          </div>
          <span className="text-ws-soft shrink-0 text-[10px] uppercase tracking-[0.18em]">
            {turn.status === 'completed'
              ? '已完成'
              : turn.status === 'error'
                ? '失败'
                : isActive
                  ? '进行中'
                  : '运行中'}
          </span>
        </div>

        {processEvents.length ? (
          <div className="space-y-2.5">
            {processEvents.map((event, index) =>
              renderTurnEvent(event, index, isActive && index === latestEventIndex),
            )}
          </div>
        ) : isActive ? (
          <div className="theme-transition text-ws-muted rounded-[14px] border ws-card-muted px-3 py-2.5 text-[12px]">
            当前轮次已创建，等待 Agent 产出过程事件。
          </div>
        ) : null}

        {turn.status === 'error' ? (
          <div className="mt-3 rounded-[14px] border border-rose-900/60 bg-rose-950/40 px-3 py-2.5 text-[12px] text-rose-200">
            {turn.error_message || '本轮执行失败。'}
          </div>
        ) : null}

        {finalEvent?.content || turn.final_text ? (
          <div className="theme-transition mt-3 rounded-[14px] border ws-card-muted px-3 py-2.5">
            <p className="text-ws-primary text-[12px] font-medium">最终输出</p>
            <p className="text-ws-secondary mt-2 whitespace-pre-wrap break-words text-[12px] leading-5">
              {finalEvent?.content || turn.final_text}
            </p>
          </div>
        ) : null}
      </div>
    </article>
  );
};
