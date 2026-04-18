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

export interface CaptionAssistantSession {
  session_id: string;
  platform: string;
  keyframes: Keyframe[];
  video_summary: string;
  frame_analyses: string[];
  execution_plan: string[];
  subtitle_draft: string;
  editing_plan: string;
  english_title: string;
  tags: string[];
  messages: ChatMessage[];
  status: 'idle' | 'queued' | 'processing' | 'completed' | 'error';
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
