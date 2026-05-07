import React from 'react';
import {
  Check,
  Circle,
  Clapperboard,
  Download,
  Film,
  Loader2,
  Sparkles,
  Subtitles,
  Video,
} from 'lucide-react';

import {
  WorkflowStateRow,
  getWorkflowStatusTone,
  getWorkflowStatusLabel,
} from './shared';
import { CaptionAssistantSession } from '../../types';
import { Button } from '../ui/button';
import { captionSessionExportedVideoUrl } from '../../api/api';

interface MobileEditStatusDrawerProps {
  session: CaptionAssistantSession | null;
  activeSessionTitle: string;
  workflowRows: WorkflowStateRow[];
}

const STEP_CONFIG = [
  { key: 'keyframe_analysis', label: '分析视频', icon: Film },
  { key: 'subtitle_draft', label: '生成字幕', icon: Subtitles },
  { key: 'editing_plan', label: '生成剪辑方案', icon: Clapperboard },
  { key: 'edited_video', label: '导出视频', icon: Video },
] as const;

const StepIcon: React.FC<{ status: string; Icon: React.FC<React.SVGProps<SVGSVGElement>> }> = ({
  status,
  Icon,
}) => {
  if (status === 'completed') {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10">
        <Check className="h-4 w-4 text-emerald-400" />
      </div>
    );
  }
  if (status === 'in_progress') {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-sky-500/30 bg-sky-500/10">
        <Loader2 className="h-4 w-4 animate-spin text-sky-400" />
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-rose-500/30 bg-rose-500/10">
        <Circle className="h-4 w-4 text-rose-400" />
      </div>
    );
  }
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b]">
      <Icon className="h-4 w-4 text-slate-500" />
    </div>
  );
};

const MobileEditStatusDrawer: React.FC<MobileEditStatusDrawerProps> = ({
  session,
  activeSessionTitle,
  workflowRows,
}) => {
  const state = session?.global_editing_state;

  if (!session || !state) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center py-12 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-800 bg-[#151515]">
          <Clapperboard className="h-6 w-6 text-slate-600" />
        </div>
        <p className="mt-4 text-[13px] font-medium text-slate-300">暂无剪辑任务</p>
        <p className="mt-1.5 max-w-[220px] text-[11px] leading-5 text-slate-500">
          提交任务后，这里会展示工具调用、字幕生成和导出进度
        </p>
      </div>
    );
  }

  const stepMap = new Map(workflowRows.map((r) => [r.key, r.item]));
  const editedVideoState = state.edited_video;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {/* Current session card */}
      <div className="shrink-0 border-b border-slate-800 px-4 py-3">
        <div className="rounded-2xl border border-slate-800 bg-[#171717] px-3 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-[#111111] text-slate-300 shadow-sm">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <p className="truncate text-[13px] font-semibold text-slate-100">
                {activeSessionTitle}
              </p>
            </div>
            <span className="shrink-0 rounded-full border border-slate-700 bg-[#111111] px-2 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
              {session.status}
            </span>
          </div>
          {state.request_summary ? (
            <p className="mt-2 line-clamp-2 text-[11px] leading-4 text-slate-400">
              {state.request_summary}
            </p>
          ) : null}
        </div>
      </div>

      {/* Workflow stepper */}
      <div className="flex-1 overflow-y-auto px-4 py-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
          工作流进度
        </p>
        <div className="space-y-0">
          {STEP_CONFIG.map((step, index) => {
            const item = stepMap.get(step.key);
            const status = item?.status ?? '未执行';
            const detail = item?.detail ?? '';
            const isLast = index === STEP_CONFIG.length - 1;
            const lineTone =
              status === 'completed'
                ? 'bg-emerald-500/30'
                : status === 'in_progress'
                  ? 'bg-sky-500/20'
                  : 'bg-slate-700/40';

            return (
              <div key={step.key} className="flex gap-3">
                {/* Vertical line + icon */}
                <div className="flex flex-col items-center">
                  <StepIcon status={status} Icon={step.icon} />
                  {!isLast && (
                    <div className={`my-1 h-6 w-px ${lineTone}`} />
                  )}
                </div>
                {/* Step content */}
                <div className={`min-w-0 flex-1 ${isLast ? '' : 'pb-4'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[12px] font-medium text-slate-200">{step.label}</p>
                    <span
                      className={`h-2 w-2 rounded-full ${getWorkflowStatusTone(status)}`}
                    />
                  </div>
                  {detail ? (
                    <p className="mt-1 text-[11px] leading-4 text-slate-500">{detail}</p>
                  ) : null}
                  <span className="mt-0.5 inline-block text-[10px] uppercase tracking-[0.14em] text-slate-500">
                    {getWorkflowStatusLabel(status)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Artifacts section */}
        {(state.subtitle_draft.trim() || state.editing_plan.trim() || state.english_title.trim()) ? (
          <div className="mt-5">
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              当前产物
            </p>
            <div className="space-y-2">
              {state.subtitle_draft.trim() ? (
                <details className="group rounded-2xl border border-slate-800 bg-[#171717]">
                  <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2">
                    <span className="text-[11px] font-medium text-slate-200">字幕草稿</span>
                    <span className="text-[10px] text-slate-500">展开</span>
                  </summary>
                  <div className="border-t border-slate-800 px-3 py-2">
                    <pre className="whitespace-pre-wrap break-words font-sans text-[11px] leading-5 text-slate-300">
                      {state.subtitle_draft.trim()}
                    </pre>
                  </div>
                </details>
              ) : null}
              {state.editing_plan.trim() ? (
                <details className="group rounded-2xl border border-slate-800 bg-[#171717]">
                  <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2">
                    <span className="text-[11px] font-medium text-slate-200">剪辑方案</span>
                    <span className="text-[10px] text-slate-500">展开</span>
                  </summary>
                  <div className="border-t border-slate-800 px-3 py-2">
                    <pre className="whitespace-pre-wrap break-words font-sans text-[11px] leading-5 text-slate-300">
                      {state.editing_plan.trim()}
                    </pre>
                  </div>
                </details>
              ) : null}
              {state.english_title.trim() ? (
                <div className="rounded-2xl border border-slate-800 bg-[#171717] px-3 py-2">
                  <p className="text-[10px] uppercase tracking-[0.14em] text-slate-500">英文标题</p>
                  <p className="mt-1 text-[12px] text-slate-300">{state.english_title.trim()}</p>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* Export section */}
        {editedVideoState?.download_url || editedVideoState?.error_message ? (
          <div className="mt-5">
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              导出成片
            </p>
            <div className="rounded-2xl border border-slate-800 bg-[#171717] px-3 py-2.5">
              <p className="text-[12px] text-slate-200">
                {editedVideoState.file_name || '暂未生成导出文件'}
              </p>
              {editedVideoState.error_message ? (
                <div className="mt-2 rounded-xl border border-rose-900/60 bg-rose-950/40 px-3 py-2 text-[11px] text-rose-200">
                  {editedVideoState.error_message}
                </div>
              ) : null}
              {session && editedVideoState.download_url ? (
                <Button
                  asChild
                  variant="secondary"
                  className="mt-3 w-full justify-center gap-2"
                >
                  <a
                    href={captionSessionExportedVideoUrl(session.session_id)}
                    download={editedVideoState.file_name || 'exported-video.mp4'}
                  >
                    <Download className="h-4 w-4" />
                    导出剪辑视频
                  </a>
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default MobileEditStatusDrawer;
