// 字幕生成相关类型
export interface CaptionResponse {
  caption: string;
  editing_plan?: string;
  keyframes?: Keyframe[];
  session_id?: string;
  response?: string;
}

export interface Keyframe {
  timestamp_seconds: number;
  frame_number: number | null;
  source: string;
  image_base64: string;
  width: number;
  height: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ExecutionPlanOption {
  id: string;
  title: string;
  description: string;
  required: boolean;
  selected: boolean;
}

export interface AgentTraceItem {
  thought: string;
  action: string;
  observation: string;
  created_at: string;
}

export interface ExecutionEventItem {
  kind: string;
  title: string;
  detail: string;
  tool: string;
  artifact: string;
  created_at: string;
}

export interface WorkflowArtifactState {
  label: string;
  status: string;
  detail: string;
  requested: boolean;
  needs_refresh: boolean;
  updated_at: string;
}

export interface EditingWorkflowState {
  request_summary: string;
  confirmation_required: boolean;
  confirmed_plan_summary: string;
  keyframe_analysis: WorkflowArtifactState;
  video_summary: WorkflowArtifactState;
  subtitle_draft: WorkflowArtifactState;
  editing_plan: WorkflowArtifactState;
  english_title: WorkflowArtifactState;
  tags: WorkflowArtifactState;
}

export interface CaptionAssistantSession {
  session_id: string;
  platform: string;
  keyframes: Keyframe[];
  video_summary: string;
  frame_analyses: string[];
  execution_plan: string[];
  plan_options: ExecutionPlanOption[];
  selected_plan_ids: string[];
  agent_trace: AgentTraceItem[];
  execution_events: ExecutionEventItem[];
  subtitle_draft: string;
  editing_plan: string;
  english_title: string;
  tags: string[];
  editing_state: EditingWorkflowState;
  planner_stream: string;
  messages: ChatMessage[];
  status:
    | 'idle'
    | 'queued'
    | 'planning'
    | 'awaiting_plan_selection'
    | 'processing'
    | 'completed'
    | 'error';
  progress_message: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface CaptionSessionEvent {
  event: string;
  data: CaptionAssistantSession | {
    session_id: string;
    status: string;
    message: string;
    updated_at: string;
  };
}

// 多Agent讨论相关类型
export interface DiscussionRequest {
  topic: string;
  requirements: string;
}

export interface DiscussionResponse {
  discussion: string[];
  topic: string;
  requirements: string;
  final_script: string;
}

// 市场调研相关类型
export interface ResearchRequest {
  product: string;
  targetMarket: string;
}

export interface ResearchResponse {
  market_trends: string;
  competitor_analysis: string;
  strategy_suggestions: string;
}
