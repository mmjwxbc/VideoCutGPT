import axios from 'axios';
import { CaptionAssistantSession } from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
});

export const captionSessionEventsUrl = (sessionId: string) =>
  `/api/caption/assistant/session/${sessionId}/events`;

// 字幕生成
export const generateCaption = async (
  video: File,
  platform: string,
  productManual: string | null,
) => {
  const formData = new FormData();
  formData.append('video', video);
  formData.append('platform', platform);
  if (productManual) {
    formData.append('product_manual', productManual);
  }

  const response = await api.post('/caption/generate', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
};

export const createCaptionAssistantSession = async (
  video: File,
  platform: string,
  prompt: string,
  productManual: string | null,
): Promise<CaptionAssistantSession> => {
  const formData = new FormData();
  formData.append('video', video);
  formData.append('platform', platform);
  formData.append('prompt', prompt);
  if (productManual) {
    formData.append('product_manual', productManual);
  }

  const response = await api.post('/caption/assistant/session', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
};

export const continueCaptionAssistantSession = async (
  sessionId: string,
  prompt: string,
): Promise<CaptionAssistantSession> => {
  const response = await api.post(
    `/caption/assistant/session/${sessionId}/message`,
    { prompt },
  );

  return response.data;
};

export const getCaptionAssistantSession = async (
  sessionId: string,
): Promise<CaptionAssistantSession> => {
  const response = await api.get(`/caption/assistant/session/${sessionId}`);
  return response.data;
};

// 多Agent讨论
export const runDiscussion = async (topic: string, requirements: string) => {
  const response = await api.post('/multi-agent/discuss', {
    topic,
    requirements,
  });

  return response.data;
};

// 市场调研
export const researchMarket = async (product: string, targetMarket: string) => {
  const response = await api.post('/deep-research/market', {
    product,
    target_market: targetMarket,
  });

  return response.data;
};

export default api;
