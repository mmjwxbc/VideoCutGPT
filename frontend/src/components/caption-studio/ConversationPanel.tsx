import React from 'react';

import ChatComposer, { ChatComposerOption } from '../ChatComposer';
import { AssistantTurnCard, ChatBubble, ExecutionGroup } from './shared';
import { CaptionAssistantSession, ChatMessage } from '../../types';

interface ConversationPanelProps {
  mobilePane: 'chat' | 'workspace';
  setMobilePane: React.Dispatch<React.SetStateAction<'chat' | 'workspace'>>;
  threadRef: React.RefObject<HTMLDivElement>;
  session: CaptionAssistantSession | null;
  messages: ChatMessage[];
  isRunning: boolean;
  progressText: string;
  executionGroups: ExecutionGroup[];
  draftPrompt: string;
  setDraftPrompt: (value: string) => void;
  submitPrompt: (value: string) => void | Promise<void>;
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
  messages,
  isRunning,
  progressText,
  executionGroups,
  draftPrompt,
  setDraftPrompt,
  submitPrompt,
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
}) => {
  const lastMessage = messages[messages.length - 1];
  const showActiveAssistantCard = Boolean(
    session &&
      (session.status === 'queued' ||
        session.status === 'planning' ||
        session.status === 'processing' ||
        session.status === 'awaiting_plan_selection') &&
      lastMessage?.role !== 'assistant',
  );

  return (
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
        执行工作区
      </button>
    </div>

    <div className={`flex min-h-0 flex-1 flex-col ${mobilePane === 'workspace' ? 'hidden lg:flex' : ''}`}>
      <div
        ref={threadRef}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#090909] px-6 py-5 [overflow-anchor:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="flex min-h-full flex-col gap-3 pb-6">
          {!session ? (
            <div className="flex min-h-[160px] items-center justify-center rounded-[18px] border border-slate-800 bg-[#141414] px-3.5 py-4 text-center">
              <div className="max-w-lg">
                <p className="text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">
                  Waiting For Session
                </p>
                <h3 className="mt-2 text-[15px] font-semibold tracking-[-0.04em] text-slate-100">
                  先在下方创建你的第一轮任务
                </h3>
                <p className="mt-2 text-[12px] leading-5 text-slate-400">
                  提交后，这里会持续显示用户要求、助手回复和后续每一轮改稿指令。
                </p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((message, index) => (
                <div key={`${message.created_at}-${index}`} className="space-y-2.5">
                  {message.role === 'assistant' && index === messages.length - 1 ? (
                    <AssistantTurnCard
                      message={message}
                      status={session?.status}
                      isRunning={isRunning}
                      progressText={progressText}
                      plannerStream={session?.planner_stream ?? ''}
                      executionGroups={executionGroups}
                    />
                  ) : (
                    <ChatBubble message={message} />
                  )}
                </div>
              ))}

              {showActiveAssistantCard ? (
                <AssistantTurnCard
                  message={{
                    role: 'assistant',
                    content: '',
                    created_at: session?.updated_at ?? new Date().toISOString(),
                  }}
                  status={session?.status}
                  isRunning={isRunning}
                  progressText={progressText}
                  plannerStream={session?.planner_stream ?? ''}
                  executionGroups={executionGroups}
                />
              ) : null}
            </>
          )}
          <div className="h-px shrink-0" />
        </div>
      </div>

      <div className={`shrink-0 bg-[#090909] px-6 pb-5 pt-4 ${mobilePane === 'workspace' ? 'hidden lg:block' : ''}`}>
        <ChatComposer
          className="mx-auto"
          value={draftPrompt}
          onChange={setDraftPrompt}
          onSubmit={(nextValue) => void submitPrompt(nextValue)}
          disabled={isRunning || session?.status === 'awaiting_plan_selection'}
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
          placeholder={
            composerMode === 'initial'
              ? '有问题，尽管问'
              : session?.status === 'awaiting_plan_selection'
                ? '请先在右侧确认 Agent 执行计划。'
                : '有问题，尽管问'
          }
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
};

export default ConversationPanel;
