import React from 'react';

import ChatComposer, { ChatComposerOption } from '../ChatComposer';
import { AgentTurn, AnalysisMode, CaptionAssistantSession } from '../../types';
import { AssistantTurnCard, ChatBubble } from './shared';

interface ConversationPanelProps {
  mobilePane: 'chat' | 'workspace';
  setMobilePane: React.Dispatch<React.SetStateAction<'chat' | 'workspace'>>;
  threadRef: React.RefObject<HTMLDivElement>;
  session: CaptionAssistantSession | null;
  turns: AgentTurn[];
  pendingUserPrompt: string | null;
  isRunning: boolean;
  draftPrompt: string;
  setDraftPrompt: (value: string) => void;
  submitPrompt: (value: string) => void | Promise<void>;
  analysisMode: AnalysisMode;
  setAnalysisMode: (value: AnalysisMode) => void;
  platform: string;
  platformOptions: ChatComposerOption[];
  setPlatform: (value: string) => void;
  composerMode: 'initial' | 'followup';
  uploadInputRef: React.RefObject<HTMLInputElement>;
  videoPreviewUrl: string | null;
  videoName: string | null;
  clearUploadedVideo?: () => void;
  productManual: string;
  setProductManual: (value: string) => void;
  sellingPointsOpen: boolean;
  setSellingPointsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  error: string;
}

const ConversationPanel: React.FC<ConversationPanelProps> = ({
  mobilePane,
  setMobilePane,
  threadRef,
  session,
  turns,
  pendingUserPrompt,
  isRunning,
  draftPrompt,
  setDraftPrompt,
  submitPrompt,
  analysisMode,
  setAnalysisMode,
  platform,
  platformOptions,
  setPlatform,
  composerMode,
  uploadInputRef,
  videoPreviewUrl,
  videoName,
  clearUploadedVideo,
  productManual,
  setProductManual,
  sellingPointsOpen,
  setSellingPointsOpen,
  error,
}) => (
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
        剪辑状态
      </button>
    </div>

    <div className={`flex min-h-0 flex-1 flex-col ${mobilePane === 'workspace' ? 'hidden lg:flex' : ''}`}>
      <div
        ref={threadRef}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#090909] px-6 py-5 [overflow-anchor:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="flex min-h-full flex-col gap-3 pb-6">
          {!session && !pendingUserPrompt ? (
            <div className="flex min-h-[160px] items-center justify-center rounded-[18px] border border-slate-800 bg-[#141414] px-3.5 py-4 text-center">
              <div className="max-w-lg">
                <p className="text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">
                  Waiting For Session
                </p>
                <h3 className="mt-2 text-[15px] font-semibold tracking-[-0.04em] text-slate-100">
                  先在下方创建你的第一轮任务
                </h3>
                <p className="mt-2 text-[12px] leading-5 text-slate-400">
                  提交后，这里只展示每一轮的工具调用参数、思考过程和最终文字输出。
                </p>
              </div>
            </div>
          ) : (
            <>
              {turns.map((turn) => (
                <div key={turn.turn_id} className="space-y-2.5">
                  <ChatBubble content={turn.user_prompt} />
                  <AssistantTurnCard
                    turn={turn}
                    isActive={session?.active_turn_id === turn.turn_id && turn.status === 'running'}
                  />
                </div>
              ))}

              {pendingUserPrompt && !turns.length ? (
                <ChatBubble content={pendingUserPrompt} />
              ) : null}
            </>
          )}
          <div className="h-px shrink-0" />
        </div>
      </div>

      <div className={`shrink-0 bg-[#090909] px-6 pb-5 pt-4 ${mobilePane === 'workspace' ? 'hidden lg:block' : ''}`}>
        <div className="mx-auto mb-3 flex w-full max-w-[960px] items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-[#141414] px-4 py-3">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">
              Analysis Mode
            </p>
            <p className="mt-1 text-[12px] text-slate-400">
              选择首轮视频理解方式。逐秒分析会读取更多帧，耗时更长。
            </p>
          </div>
          <div className="inline-flex rounded-full border border-white/10 bg-[#1d1d1d] p-1">
            {([
              ['keyframe', '关键帧分析'],
              ['every_second', '逐秒分析'],
            ] as const).map(([value, label]) => {
              const selected = analysisMode === value;
              const disabled = composerMode !== 'initial' || isRunning;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    if (!disabled) {
                      setAnalysisMode(value);
                    }
                  }}
                  disabled={disabled}
                  className={`inline-flex h-9 items-center justify-center rounded-full px-3.5 text-[12px] font-medium transition ${
                    selected
                      ? 'bg-sky-500/15 text-sky-200'
                      : 'text-slate-400 hover:text-slate-200'
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        <ChatComposer
          className="mx-auto"
          value={draftPrompt}
          onChange={setDraftPrompt}
          onSubmit={(nextValue) => void submitPrompt(nextValue)}
          disabled={isRunning}
          platform={platform}
          platformOptions={platformOptions}
          onPlatformChange={setPlatform}
          onUploadClick={() => {
            if (composerMode !== 'initial') {
              return;
            }
            uploadInputRef.current?.click();
          }}
          uploadPreviewUrl={composerMode === 'initial' ? videoPreviewUrl : null}
          uploadPreviewName={composerMode === 'initial' ? videoName : null}
          onClearUploadPreview={composerMode === 'initial' ? clearUploadedVideo : undefined}
          sellingPointsValue={productManual}
          onSellingPointsChange={setProductManual}
          sellingPointsOpen={sellingPointsOpen}
          onSellingPointsToggle={() => setSellingPointsOpen((current) => !current)}
          toolsDisabled={composerMode !== 'initial' || isRunning}
          placeholder="有问题，尽管问"
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
);

export default ConversationPanel;
