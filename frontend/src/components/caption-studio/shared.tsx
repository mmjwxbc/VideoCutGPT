import React from 'react';
import { Bot, ChevronDown, User, Wrench } from 'lucide-react';

import {
  AgentTurn,
  CaptionAssistantSession,
  EditingWorkflowState,
  TurnEventItem,
  WorkflowArtifactState,
} from '../../types';

export interface SessionListItem {
  session_id: string;
  title: string;
  subtitle: string;
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

const panelClassName = 'border border-slate-800 bg-[#111111]';

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
    updated_at: nextSession.updated_at,
  };
};

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

export const ChatBubble: React.FC<ChatBubbleProps> = ({ content }) => (
  <article className="flex w-full items-start gap-2.5 justify-end pl-10 sm:pl-24">
    <div className="w-fit max-w-[min(72%,34rem)] min-w-0 rounded-2xl bg-[#2a2a2a] px-3 py-2.5 text-white shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
      <div className="mb-1 flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
        <span className="text-white/60">You</span>
      </div>
      <p className="whitespace-pre-wrap break-words text-[12px] leading-5">{content}</p>
    </div>
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-300 shadow-sm">
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
    className="group rounded-[14px] border border-slate-800 bg-[#1b1b1b]"
  >
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
      <div className="flex min-w-0 items-center gap-2">
        {icon}
        <p className="truncate text-[12px] font-medium text-slate-100">{title}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="text-[10px] text-slate-500">{formatTimestamp(timestamp)}</span>
        <ChevronDown className="h-3.5 w-3.5 text-slate-500 transition group-open:rotate-180" />
      </div>
    </summary>
    <div className="border-t border-slate-800 px-3 py-2.5">
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
        icon={<Wrench className="h-3.5 w-3.5 text-slate-400" />}
        defaultOpen={defaultOpen}
      >
        <pre className="whitespace-pre-wrap break-words rounded-[12px] border border-slate-800 bg-[#121212] px-3 py-2 text-[11px] leading-5 text-slate-400">
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
        <p className="whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-400">
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
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-100 shadow-sm">
        <Bot className="h-3 w-3" />
      </div>

      <div className="w-full max-w-[min(92%,52rem)] rounded-2xl border border-slate-800 bg-[#161616] px-3 py-2.5 text-slate-300 shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
        <div className="mb-3 flex items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
            <span className="text-slate-500">Assistant</span>
          </div>
          <span className="shrink-0 text-[10px] uppercase tracking-[0.18em] text-slate-500">
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
          <div className="rounded-[14px] border border-slate-800 bg-[#1b1b1b] px-3 py-2.5 text-[12px] text-slate-400">
            当前轮次已创建，等待 Agent 产出过程事件。
          </div>
        ) : null}

        {turn.status === 'error' ? (
          <div className="mt-3 rounded-[14px] border border-rose-900/60 bg-rose-950/40 px-3 py-2.5 text-[12px] text-rose-200">
            {turn.error_message || '本轮执行失败。'}
          </div>
        ) : null}

        {finalEvent?.content || turn.final_text ? (
          <div className="mt-3 rounded-[14px] border border-slate-800 bg-[#1b1b1b] px-3 py-2.5">
            <p className="text-[12px] font-medium text-slate-100">最终输出</p>
            <p className="mt-2 whitespace-pre-wrap break-words text-[12px] leading-5 text-slate-300">
              {finalEvent?.content || turn.final_text}
            </p>
          </div>
        ) : null}
      </div>
    </article>
  );
};
