import axios from 'axios';
import { CaptionAssistantSession } from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
});

export const captionSessionEventsUrl = (sessionId: string) =>
  `/api/caption/assistant/session/${sessionId}/events`;

export const captionSessionExportedVideoUrl = (sessionId: string) =>
  `/api/caption/assistant/session/${sessionId}/exported-video`;

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

export default api;
