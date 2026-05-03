import React from 'react';
import { ChevronDown, Download, Sparkles } from 'lucide-react';

import { Panel, WorkflowStateRow, WorkflowStepCard, getWorkflowStatusLabel, getWorkflowStatusTone } from './shared';
import { CaptionAssistantSession } from '../../types';
import { Button } from '../ui/button';
import { captionSessionExportedVideoUrl } from '../../api/api';

interface WorkspaceSidebarProps {
  mobilePane: 'chat' | 'workspace';
  session: CaptionAssistantSession | null;
  activeSessionTitle: string;
  workflowRows: WorkflowStateRow[];
}

interface ArtifactCardProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  accentClassName?: string;
}

const ArtifactCard: React.FC<ArtifactCardProps> = ({
  title,
  children,
  defaultOpen = false,
  accentClassName = 'text-slate-500',
}) => (
  <details
    open={defaultOpen}
    className="group rounded-[14px] border border-slate-800 bg-[#111111]"
  >
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2">
      <div className={`text-[11px] uppercase tracking-[0.18em] ${accentClassName}`}>
        {title}
      </div>
      <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-500 transition group-open:rotate-180" />
    </summary>
    <div className="border-t border-slate-800 px-3 py-2">
      {children}
    </div>
  </details>
);

const WorkspaceSidebar: React.FC<WorkspaceSidebarProps> = ({
  mobilePane,
  session,
  activeSessionTitle,
  workflowRows,
}) => {
  const state = session?.global_editing_state;
  const editedVideoState = state?.workflow.edited_video;
  const showEditedVideoCard = Boolean(
    state?.edited_video.download_url ||
      state?.edited_video.error_message ||
      editedVideoState?.requested,
  );
  const hasArtifacts = Boolean(
    state?.subtitle_draft.trim() ||
      state?.editing_plan.trim() ||
      state?.english_title.trim() ||
      state?.tags.length ||
      state?.video_summary.trim() ||
      state?.frame_analyses.length ||
      showEditedVideoCard,
  );

  return (
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
                    {session ? activeSessionTitle : '全局剪辑状态'}
                  </p>
                </div>
              </div>
              <span className="shrink-0 rounded-full border border-slate-700 bg-[#111111] px-2 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
                {session?.status || 'idle'}
              </span>
            </div>
            <p className="mt-1.5 line-clamp-2 text-[11px] leading-4 text-slate-400" aria-live="polite">
              {state?.request_summary || '当前轮次结束后，右侧会展示提交后的全局视频剪辑状态。'}
            </p>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto pt-2 pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {state ? (
              <div className="space-y-2.5">
                <WorkflowStepCard
                  title="剪辑状态"
                  status={session?.status === 'completed' ? 'completed' : 'active'}
                  defaultOpen
                >
                  <div className="space-y-2 text-[12px] leading-5 text-slate-400">
                    <div className="rounded-[14px] border border-slate-800 bg-[#111111] px-3 py-2">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                        Request
                      </div>
                      <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-slate-300">
                        {state.request_summary || '暂无'}
                      </p>
                    </div>
                    {workflowRows.map(({ key, item }: WorkflowStateRow) => (
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
                      </div>
                    ))}
                  </div>
                </WorkflowStepCard>

                <WorkflowStepCard
                  title="当前产物"
                  status={session?.status === 'completed' ? 'completed' : 'active'}
                  defaultOpen
                >
                  <div className="space-y-2 text-[12px] leading-5 text-slate-400">
                    {state.subtitle_draft.trim() ? (
                      <ArtifactCard title="字幕草稿" defaultOpen>
                        <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-[12px] text-slate-300">
                          {state.subtitle_draft.trim()}
                        </pre>
                      </ArtifactCard>
                    ) : null}
                    {state.editing_plan.trim() ? (
                      <ArtifactCard title="剪辑方案">
                        <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-[12px] text-slate-300">
                          {state.editing_plan.trim()}
                        </pre>
                      </ArtifactCard>
                    ) : null}
                    {state.english_title.trim() ? (
                      <ArtifactCard title="英文标题">
                        <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-slate-300">
                          {state.english_title.trim()}
                        </p>
                      </ArtifactCard>
                    ) : null}
                    {state.tags.length ? (
                      <ArtifactCard title="标签">
                        <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-slate-300">
                          {state.tags.join(', ')}
                        </p>
                      </ArtifactCard>
                    ) : null}
                    {state.video_summary.trim() ? (
                      <ArtifactCard title="视频摘要">
                        <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-[12px] text-slate-300">
                          {state.video_summary.trim()}
                        </pre>
                      </ArtifactCard>
                    ) : null}
                    {state.frame_analyses.length ? (
                      <ArtifactCard title="关键帧理解">
                        <div className="mt-1 space-y-2">
                          {state.frame_analyses.slice(0, 6).map((item, index) => (
                            <p
                              key={`${index}-${item.slice(0, 12)}`}
                              className="whitespace-pre-wrap break-words text-[12px] text-slate-300"
                            >
                              {item}
                            </p>
                          ))}
                        </div>
                      </ArtifactCard>
                    ) : null}
                    {showEditedVideoCard ? (
                      <ArtifactCard
                        title="导出成片"
                        accentClassName={
                          state.edited_video.download_url
                            ? 'text-emerald-300/80'
                            : state.edited_video.error_message
                              ? 'text-rose-300/80'
                              : 'text-slate-400'
                        }
                      >
                        <div className="mt-1 space-y-2">
                          <p className="break-words text-[12px] text-slate-200">
                            {state.edited_video.file_name || '暂未生成导出文件'}
                          </p>
                          {state.edited_video.summary ? (
                            <p className="whitespace-pre-wrap break-words text-[12px] text-slate-400">
                              {state.edited_video.summary}
                            </p>
                          ) : null}
                          {state.edited_video.error_message ? (
                            <div className="rounded-[12px] border border-rose-900/60 bg-rose-950/40 px-3 py-2 text-[12px] text-rose-200">
                              {state.edited_video.error_message}
                            </div>
                          ) : null}
                          {state.edited_video.size_bytes > 0 ? (
                            <p className="text-[11px] text-slate-500">
                              {(state.edited_video.size_bytes / (1024 * 1024)).toFixed(2)} MB
                            </p>
                          ) : null}
                          {state.edited_video.command ? (
                            <div className="rounded-[12px] border border-slate-800 bg-[#0b0b0b] px-3 py-2">
                              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                                FFmpeg Command
                              </div>
                              <pre className="mt-1 whitespace-pre-wrap break-words font-sans text-[11px] leading-5 text-slate-400">
                                {state.edited_video.command}
                              </pre>
                            </div>
                          ) : null}
                          {session && state.edited_video.download_url ? (
                            <Button
                              asChild
                              variant="secondary"
                              className="w-full justify-center gap-2"
                            >
                              <a
                                href={captionSessionExportedVideoUrl(session.session_id)}
                                download={state.edited_video.file_name || 'exported-video.mp4'}
                              >
                                <Download className="h-4 w-4" />
                                导出剪辑视频
                              </a>
                            </Button>
                          ) : (
                            <div className="rounded-[12px] border border-dashed border-slate-800 bg-[#0b0b0b] px-3 py-2 text-[11px] text-slate-500">
                              当前还没有可下载成片。请先修复导出参数或重新执行导出。
                            </div>
                          )}
                        </div>
                      </ArtifactCard>
                    ) : null}
                    {!hasArtifacts ? (
                      <div className="rounded-[14px] border border-dashed border-slate-800 bg-[#111111] px-3 py-2 text-[12px] text-slate-500">
                        当前还没有已提交的剪辑状态产物。
                      </div>
                    ) : null}
                  </div>
                </WorkflowStepCard>
              </div>
            ) : (
              <div className="rounded-[18px] border border-dashed border-slate-800 bg-[#151515] px-4 py-5 text-[13px] leading-5 text-slate-400">
                当前轮次结束后，新的全局视频剪辑状态会显示在这里。
              </div>
            )}
          </div>
        </div>
      </Panel>
    </aside>
  );
};

export default WorkspaceSidebar;
