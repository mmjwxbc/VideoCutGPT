import React from 'react';

import ChatComposer, { ChatComposerOption } from '../ChatComposer';
import MobileDrawerTabs, { DrawerType } from './MobileDrawerTabs';
import { AgentTurn, AnalysisMode, CaptionAssistantSession } from '../../types';
import { AssistantTurnCard, ChatBubble, SessionListItem, WorkflowStateRow } from './shared';

interface ConversationPanelProps {
  activeDrawer: DrawerType | null;
  onToggleDrawer: (type: DrawerType) => void;
  onCloseDrawer: () => void;
  sessionHistory: SessionListItem[];
  activeSessionId?: string;
  loadingSessionId?: string | null;
  isSessionLoading: boolean;
  onOpenSession: (sessionId: string) => void | Promise<void>;
  onReset: () => void;
  threadRef: React.RefObject<HTMLDivElement>;
  session: CaptionAssistantSession | null;
  turns: AgentTurn[];
  pendingUserPrompt: string | null;
  isRunning: boolean;
  submitDisabled: boolean;
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
  uploadPreviews: Array<{
    url: string;
    name: string;
    progress: number;
    status: 'idle' | 'uploading' | 'processing' | 'done' | 'failed';
  }>;
  selectedUploadIndex: number;
  onSelectUpload: (index: number) => void;
  onMoveUpload: (fromIndex: number, toIndex: number) => void;
  clearUploadedVideo?: () => void;
  productManual: string;
  setProductManual: (value: string) => void;
  sellingPointsOpen: boolean;
  setSellingPointsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  error: string;
  accessRecoveryRequired?: boolean;
  errorActions?: React.ReactNode;
  isSubmitting: boolean;
  activeSessionTitle: string;
  workflowRows: WorkflowStateRow[];
}

const ConversationPanel: React.FC<ConversationPanelProps> = ({
  activeDrawer,
  onToggleDrawer,
  onCloseDrawer,
  sessionHistory,
  activeSessionId,
  loadingSessionId,
  isSessionLoading,
  onOpenSession,
  onReset,
  threadRef,
  session,
  turns,
  pendingUserPrompt,
  isRunning,
  submitDisabled,
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
  uploadPreviews,
  selectedUploadIndex,
  onSelectUpload,
  onMoveUpload,
  clearUploadedVideo,
  productManual,
  setProductManual,
  sellingPointsOpen,
  setSellingPointsOpen,
  error,
  accessRecoveryRequired = false,
  errorActions,
  isSubmitting,
  activeSessionTitle,
  workflowRows,
}) => (
  <section className="flex min-h-0 flex-col overflow-hidden bg-[#090909]">
    {/* Mobile drawer tabs (replaces old tab toggle) */}
    <MobileDrawerTabs
      activeDrawer={activeDrawer}
      onToggleDrawer={onToggleDrawer}
      onCloseDrawer={onCloseDrawer}
      sessionHistory={sessionHistory}
      activeSessionId={activeSessionId}
      loadingSessionId={loadingSessionId}
      onOpenSession={onOpenSession}
      onReset={onReset}
      session={session}
      activeSessionTitle={activeSessionTitle}
      workflowRows={workflowRows}
    />

    {/* Chat thread - always visible on mobile now */}
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={threadRef}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#090909] px-6 py-5 [overflow-anchor:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="flex min-h-full flex-col gap-3 pb-6">
          {isSessionLoading ? (
            <div className="flex min-h-[160px] items-center justify-center rounded-[18px] border border-slate-800 bg-[#141414] px-3.5 py-4 text-center">
              <div>
                <p className="text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">
                  Loading Session
                </p>
                <p className="mt-2 text-[12px] leading-5 text-slate-300">
                  正在加载会话内容，请稍候。
                </p>
              </div>
            </div>
          ) : !session && !pendingUserPrompt ? (
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

      <div className="shrink-0 bg-[#090909] px-6 pb-5 pt-4">
        <ChatComposer
          className="mx-auto"
          value={draftPrompt}
          onChange={setDraftPrompt}
          onSubmit={(nextValue) => void submitPrompt(nextValue)}
          disabled={submitDisabled}
          platform={platform}
          platformOptions={platformOptions}
          onPlatformChange={setPlatform}
          onUploadClick={() => {
            if (composerMode !== 'initial') {
              return;
            }
            uploadInputRef.current?.click();
          }}
          uploadPreviews={composerMode === 'initial' ? uploadPreviews : []}
          selectedUploadIndex={selectedUploadIndex}
          onSelectUpload={onSelectUpload}
          onMoveUpload={onMoveUpload}
          onClearUploadPreview={composerMode === 'initial' ? clearUploadedVideo : undefined}
          analysisMode={analysisMode}
          onAnalysisModeChange={setAnalysisMode}
          sellingPointsValue={productManual}
          onSellingPointsChange={setProductManual}
          sellingPointsOpen={sellingPointsOpen}
          onSellingPointsToggle={() => setSellingPointsOpen((current) => !current)}
          toolsDisabled={composerMode !== 'initial' || isRunning}
          placeholder="有问题，尽管问"
          isSubmitting={isSubmitting}
        />

        {error && !accessRecoveryRequired ? (
          <div
            className="mx-auto mt-3 w-full max-w-[960px] rounded-2xl border border-rose-900/60 bg-rose-950/40 px-4 py-3 text-[12px] text-rose-200"
            aria-live="polite"
          >
            <p>{error}</p>
            {errorActions ? <div className="mt-3 flex flex-wrap gap-2">{errorActions}</div> : null}
          </div>
        ) : null}
      </div>
    </div>

    {accessRecoveryRequired && error ? (
      <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/60 px-6">
        <div
          className="w-full max-w-md rounded-[28px] border border-rose-900/70 bg-[#12090b] p-6 text-center shadow-2xl shadow-black/40"
          aria-live="assertive"
          role="dialog"
          aria-modal="true"
        >
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-rose-300/70">
            Access Required
          </p>
          <h3 className="mt-3 text-[20px] font-semibold tracking-[-0.04em] text-rose-50">
            需要重新认证
          </h3>
          <p className="mt-3 text-[13px] leading-6 text-rose-100/85">{error}</p>
          {errorActions ? (
            <div className="mt-5 flex flex-wrap items-center justify-center gap-3">{errorActions}</div>
          ) : null}
        </div>
      </div>
    ) : null}
  </section>
);

export default ConversationPanel;
