export interface CaptionResponse {
  caption: string;
  editing_plan?: string;
  keyframes?: Keyframe[];
  session_id?: string;
  response?: string;
  exported_video?: EditedVideoArtifact;
}

export interface Keyframe {
  timestamp_seconds: number;
  frame_number: number | null;
  source: string;
  image_base64: string;
  width: number;
  height: number;
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
  keyframe_analysis: WorkflowArtifactState;
  video_summary: WorkflowArtifactState;
  subtitle_draft: WorkflowArtifactState;
  editing_plan: WorkflowArtifactState;
  english_title: WorkflowArtifactState;
  tags: WorkflowArtifactState;
  edited_video: WorkflowArtifactState;
}

export interface EditedVideoArtifact {
  file_name: string;
  download_url: string;
  command: string;
  summary: string;
  error_message: string;
  size_bytes: number;
  created_at: string;
}

export interface GlobalEditingState {
  request_summary: string;
  keyframes: Keyframe[];
  frame_analyses: string[];
  video_summary: string;
  subtitle_draft: string;
  editing_plan: string;
  english_title: string;
  tags: string[];
  edited_video: EditedVideoArtifact;
  workflow: EditingWorkflowState;
  updated_at: string;
}

export interface TurnEventItem {
  type: 'thought' | 'tool_call' | 'final_text';
  content: string;
  tool_name: string;
  arguments: string;
  created_at: string;
}

export interface AgentTurn {
  turn_id: string;
  user_prompt: string;
  status: 'running' | 'completed' | 'error';
  events: TurnEventItem[];
  final_text: string;
  error_message: string;
  started_at: string;
  finished_at: string;
}

export interface CaptionAssistantSession {
  session_id: string;
  platform: string;
  turns: AgentTurn[];
  global_editing_state: GlobalEditingState;
  status: 'idle' | 'processing' | 'completed' | 'error';
  active_turn_id: string;
  error_message: string;
  version: number;
  created_at: string;
  updated_at: string;
}
