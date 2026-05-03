import React from 'react';

import { Button } from '../ui/button';
import {
  ExecutionGroup,
  Panel,
  WorkflowStateRow,
  WorkflowStepCard,
  getWorkflowStatusLabel,
  getWorkflowStatusTone,
} from './shared';
import { CaptionAssistantSession, ExecutionPlanOption } from '../../types';
import { Sparkles } from 'lucide-react';

interface WorkspaceSidebarProps {
  mobilePane: 'chat' | 'workspace';
  session: CaptionAssistantSession | null;
  activeSessionTitle: string;
  progressText: string;
  hasWorkspaceReply: boolean;
  planOptions: ExecutionPlanOption[];
  selectedPlanIds: string[];
  togglePlanOption: (option: ExecutionPlanOption) => void;
  currentExecutionGroup: ExecutionGroup | null;
  isRunning: boolean;
  workflowRows: WorkflowStateRow[];
  onConfirmPlan: () => void | Promise<void>;
}

const WorkspaceSidebar: React.FC<WorkspaceSidebarProps> = ({
  mobilePane,
  session,
  activeSessionTitle,
  progressText,
  hasWorkspaceReply,
  planOptions,
  selectedPlanIds,
  togglePlanOption,
  currentExecutionGroup,
  isRunning,
  workflowRows,
  onConfirmPlan,
}) => (
  <aside
    className={`min-h-0 overflow-hidden bg-[#0f0f0f] ${
      mobilePane === 'chat' ? 'hidden lg:block' : ''
    }`}
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

              <WorkflowStepCard
                title="当前产物"
                status={session.status === 'completed' ? 'completed' : 'active'}
                defaultOpen
              >
                <div className="space-y-2 text-[12px] leading-5 text-slate-400">
                  {session.subtitle_draft.trim() ? (
                    <div className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                        字幕草稿
                      </div>
                      <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-[12px] text-slate-300">
                        {session.subtitle_draft.trim()}
                      </pre>
                    </div>
                  ) : null}
                  {session.editing_plan.trim() ? (
                    <div className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                        剪辑方案
                      </div>
                      <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-[12px] text-slate-300">
                        {session.editing_plan.trim()}
                      </pre>
                    </div>
                  ) : null}
                  {session.english_title.trim() ? (
                    <div className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                        英文标题
                      </div>
                      <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-slate-300">
                        {session.english_title.trim()}
                      </p>
                    </div>
                  ) : null}
                  {session.tags.length ? (
                    <div className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                        标签
                      </div>
                      <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-slate-300">
                        {session.tags.join(', ')}
                      </p>
                    </div>
                  ) : null}
                  {session.video_summary.trim() ? (
                    <div className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                        视频摘要
                      </div>
                      <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-[12px] text-slate-300">
                        {session.video_summary.trim()}
                      </pre>
                    </div>
                  ) : null}
                  {!session.subtitle_draft.trim() &&
                  !session.editing_plan.trim() &&
                  !session.english_title.trim() &&
                  !session.tags.length &&
                  !session.video_summary.trim() ? (
                    <div className="rounded-[14px] border border-dashed border-slate-800 bg-[#111111] px-3 py-2 text-[12px] text-slate-500">
                      工具执行完成后，最新结构体产物会展示在这里。
                    </div>
                  ) : null}
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
                onClick={() => void onConfirmPlan()}
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
);

export default WorkspaceSidebar;
