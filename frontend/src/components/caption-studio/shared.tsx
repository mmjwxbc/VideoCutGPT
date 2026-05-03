import React from 'react';
import { Bot, ChevronDown, User } from 'lucide-react';

import {
  CaptionAssistantSession,
  ChatMessage,
  EditingWorkflowState,
  ExecutionEventItem,
  WorkflowArtifactState,
} from '../../types';

export interface SessionListItem {
  session_id: string;
  title: string;
  subtitle: string;
  updated_at: string;
}

export interface ExecutionGroup {
  parent: ExecutionEventItem;
  children: ExecutionEventItem[];
}

export interface AssistantArtifactSection {
  title: string;
  content: string;
  defaultOpen?: boolean;
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
  message: ChatMessage;
}

interface WorkflowStepCardProps {
  title: string;
  status: 'pending' | 'active' | 'completed';
  children: React.ReactNode;
  defaultOpen?: boolean;
}

interface AssistantTurnCardProps {
  message: ChatMessage;
  status: CaptionAssistantSession['status'] | undefined;
  isRunning: boolean;
  progressText: string;
  plannerStream: string;
  executionGroups: ExecutionGroup[];
}

const panelClassName = 'border border-slate-800 bg-[#111111]';

export const formatTimestamp = (value: string) =>
  new Date(value).toLocaleString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    month: 'numeric',
    day: 'numeric',
  });

export const formatSeconds = (value: number) => {
  const totalSeconds = Math.max(0, Math.floor(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds
    .toString()
    .padStart(2, '0')}`;
};

export const buildSessionHistoryItem = (
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
    nextSession.messages[nextSession.messages.length - 1]?.content ||
    nextSession.video_summary ||
    nextSession.progress_message ||
    previousItem?.subtitle ||
    '等待处理';

  return {
    session_id: nextSession.session_id,
    title: titleSource.trim().slice(0, 28) || '未命名会话',
    subtitle: subtitleSource.trim().slice(0, 42) || '等待处理',
    updated_at: nextSession.updated_at,
  };
};

export const buildAssistantArtifactSections = (
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

export const groupExecutionEvents = (events: ExecutionEventItem[]): ExecutionGroup[] => {
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
      return '待确认';
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

export const ChatBubble: React.FC<ChatBubbleProps> = ({ message }) => {
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

export const AssistantTurnCard: React.FC<AssistantTurnCardProps> = ({
  message,
  status,
  isRunning,
  progressText,
  plannerStream,
  executionGroups,
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
                        open={
                          item.kind === 'tool_completed' ||
                          childIndex === group.children.length - 1
                        }
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
    </div>
  </article>
);
