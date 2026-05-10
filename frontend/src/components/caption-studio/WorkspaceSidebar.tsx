import React from 'react';
import { ChevronDown, Download, Sparkles } from 'lucide-react';

import { Panel, WorkflowStateRow, WorkflowStepCard, getSessionStatusLabel, getWorkflowStatusLabel, getWorkflowStatusTone } from './shared';
import { CaptionAssistantSession } from '../../types';
import { Button } from '../ui/button';
import { captionSessionExportedVideoUrl } from '../../api/api';

interface WorkspaceSidebarProps {
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
  accentClassName = 'text-ws-soft',
}) => (
  <details
    open={defaultOpen}
    className="theme-transition group rounded-[14px] border ws-card-muted"
  >
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2">
      <div className={`text-[11px] uppercase tracking-[0.18em] ${accentClassName}`}>
        {title}
      </div>
      <ChevronDown className="text-ws-soft h-3.5 w-3.5 shrink-0 transition group-open:rotate-180" />
    </summary>
    <div className="border-ws border-t px-3 py-2">
      {children}
    </div>
  </details>
);

const WorkspaceSidebar: React.FC<WorkspaceSidebarProps> = ({
  session,
  activeSessionTitle,
  workflowRows,
}) => {
  const state = session?.global_editing_state;
  const workflow = state?.workflow;
  const editedVideoState = workflow?.edited_video;
  const subtitleDraft = state?.subtitle_draft ?? '';
  const editingPlan = state?.editing_plan ?? '';
  const englishTitle = state?.english_title ?? '';
  const tags = state?.tags ?? [];
  const videoSummary = state?.video_summary ?? '';
  const frameAnalyses = state?.frame_analyses ?? [];
  const showEditedVideoCard = Boolean(
    state?.edited_video.download_url ||
      state?.edited_video.error_message ||
      editedVideoState?.requested,
  );
  const hasArtifacts = Boolean(
    subtitleDraft.trim() ||
      editingPlan.trim() ||
      englishTitle.trim() ||
      tags.length ||
      videoSummary.trim() ||
      frameAnalyses.length ||
      showEditedVideoCard,
  );

  return (
    <aside className="theme-transition ws-panel hidden min-h-0 overflow-hidden lg:block">
      <Panel
        title=""
        className="h-full overflow-hidden border-0 bg-transparent shadow-none"
        bodyClassName="flex min-h-0 flex-1 flex-col gap-2 p-0"
        hideHeader
      >
        <div className="flex h-full min-h-0 flex-col px-3.5 py-3">
          <div className="theme-transition ws-card shrink-0 rounded-[18px] border px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <div className="theme-transition ws-icon text-ws-secondary flex h-7 w-7 shrink-0 items-center justify-center rounded-full border shadow-sm">
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <p className="text-ws-primary truncate text-[13px] font-semibold">
                    {session ? activeSessionTitle : '全局剪辑状态'}
                  </p>
                </div>
              </div>
              <span className="theme-transition ws-chip text-ws-muted shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium uppercase tracking-[0.18em]">
                {getSessionStatusLabel(session?.status)}
              </span>
            </div>
            <p className="text-ws-muted mt-1.5 line-clamp-2 text-[11px] leading-4" aria-live="polite">
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
                  <div className="text-ws-muted space-y-2 text-[12px] leading-5">
                    <div className="theme-transition ws-card-muted rounded-[14px] border px-3 py-2">
                      <div className="text-ws-soft text-[11px] uppercase tracking-[0.18em]">
                        Request
                      </div>
                      <p className="text-ws-secondary mt-1 whitespace-pre-wrap break-words text-[12px]">
                        {state.request_summary || '暂无'}
                      </p>
                    </div>
                    {workflowRows.map(({ key, item }: WorkflowStateRow) => (
                      <div
                        key={key}
                        className="theme-transition ws-card-muted rounded-[14px] border px-3 py-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-2">
                            <span
                              className={`h-2 w-2 rounded-full ${getWorkflowStatusTone(item.status)}`}
                            />
                            <p className="text-ws-secondary truncate text-[12px] font-medium">
                              {item.label}
                            </p>
                          </div>
                          <span className="text-ws-soft text-[10px] uppercase tracking-[0.18em]">
                            {getWorkflowStatusLabel(item.status)}
                          </span>
                        </div>
                        <p className="text-ws-muted mt-1 text-[11px] leading-4">
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
                  <div className="text-ws-muted space-y-2 text-[12px] leading-5">
                    {subtitleDraft.trim() ? (
                      <ArtifactCard title="剪辑草稿" defaultOpen>
                        <pre className="text-ws-secondary mt-1 whitespace-pre-wrap break-words font-sans text-[12px]">
                          {subtitleDraft.trim()}
                        </pre>
                      </ArtifactCard>
                    ) : null}
                    {editingPlan.trim() ? (
                      <ArtifactCard title="剪辑方案">
                        <pre className="text-ws-secondary mt-1 whitespace-pre-wrap break-words font-sans text-[12px]">
                          {editingPlan.trim()}
                        </pre>
                      </ArtifactCard>
                    ) : null}
                    {englishTitle.trim() ? (
                      <ArtifactCard title="英文标题">
                        <p className="text-ws-secondary mt-1 whitespace-pre-wrap break-words text-[12px]">
                          {englishTitle.trim()}
                        </p>
                      </ArtifactCard>
                    ) : null}
                    {tags.length ? (
                      <ArtifactCard title="标签">
                        <p className="text-ws-secondary mt-1 whitespace-pre-wrap break-words text-[12px]">
                          {tags.join(', ')}
                        </p>
                      </ArtifactCard>
                    ) : null}
                    {videoSummary.trim() ? (
                      <ArtifactCard title="视频摘要">
                        <pre className="text-ws-secondary mt-1 whitespace-pre-wrap break-words font-sans text-[12px]">
                          {videoSummary.trim()}
                        </pre>
                      </ArtifactCard>
                    ) : null}
                    {frameAnalyses.length ? (
                      <ArtifactCard title="关键帧理解">
                        <div className="mt-1 space-y-2">
                          {frameAnalyses.slice(0, 6).map((item, index) => (
                            <p
                              key={`${index}-${item.slice(0, 12)}`}
                              className="text-ws-secondary whitespace-pre-wrap break-words text-[12px]"
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
                              : 'text-ws-muted'
                        }
                      >
                        <div className="mt-1 space-y-2">
                          <p className="text-ws-secondary break-words text-[12px]">
                            {state.edited_video.file_name || '暂未生成导出文件'}
                          </p>
                          {state.edited_video.summary ? (
                            <p className="text-ws-muted whitespace-pre-wrap break-words text-[12px]">
                              {state.edited_video.summary}
                            </p>
                          ) : null}
                          {state.edited_video.error_message ? (
                            <div className="rounded-[12px] border border-rose-900/60 bg-rose-950/40 px-3 py-2 text-[12px] text-rose-200">
                              {state.edited_video.error_message}
                            </div>
                          ) : null}
                          {state.edited_video.size_bytes > 0 ? (
                            <p className="text-ws-soft text-[11px]">
                              {(state.edited_video.size_bytes / (1024 * 1024)).toFixed(2)} MB
                            </p>
                          ) : null}
                          {state.edited_video.command ? (
                            <div className="theme-transition ws-card-contrast rounded-[12px] border px-3 py-2">
                              <div className="text-ws-soft text-[10px] uppercase tracking-[0.18em]">
                                FFmpeg Command
                              </div>
                              <pre className="text-ws-muted mt-1 whitespace-pre-wrap break-words font-sans text-[11px] leading-5">
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
                            <div className="theme-transition ws-card-contrast text-ws-soft rounded-[12px] border border-dashed px-3 py-2 text-[11px]">
                              当前还没有可下载成片。请先修复导出参数或重新执行导出。
                            </div>
                          )}
                        </div>
                      </ArtifactCard>
                    ) : null}
                    {!hasArtifacts ? (
                      <div className="theme-transition ws-card-muted text-ws-soft rounded-[14px] border border-dashed px-3 py-2 text-[12px]">
                        当前还没有已提交的剪辑状态产物。
                      </div>
                    ) : null}
                  </div>
                </WorkflowStepCard>
              </div>
            ) : (
              <div className="theme-transition ws-empty text-ws-muted rounded-[18px] border border-dashed px-4 py-5 text-[13px] leading-5">
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
