import apiClient from './client';

// Types
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
}

export interface ChatResponse {
  success?: boolean;
  message?: string;
  response?: string;
  timestamp?: number;
}

export interface SystemStatus {
  status: 'online' | 'offline' | 'error';
  uptime: number;
  version: string;
  services: {
    telegram: boolean;
    discord: boolean;
    web: boolean;
  };
}

export interface DiscordStatus {
  connected: boolean;
  serverName: string;
  channelCount: number;
  lastActivity: number;
}

export interface HealthCheck {
  healthy: boolean;
  latency: number;
  timestamp: number;
}

export interface ActivityLogEntry {
  id: string;
  type: 'chat' | 'command' | 'system' | 'discord';
  description: string;
  timestamp: number;
  metadata?: Record<string, any>;
}

// Chat Service
export const chatService = {
  sendMessage: async (message: string): Promise<ChatResponse> => {
    return apiClient.post<ChatResponse>('/chat', { message });
  },

  getHistory: async (limit = 50): Promise<ChatMessage[]> => {
    return apiClient.get<ChatMessage[]>('/chat/history', { limit });
  },

  clearHistory: async (): Promise<void> => {
    await apiClient.post('/chat/clear');
  },

  checkHealth: async (): Promise<HealthCheck> => {
    return apiClient.get<HealthCheck>('/health');
  },
};

// System Service
export const systemService = {
  getStatus: async (): Promise<SystemStatus> => {
    return apiClient.get<SystemStatus>('/status');
  },

  getHealth: async (): Promise<HealthCheck> => {
    return apiClient.get<HealthCheck>('/health');
  },

  restart: async (service?: string): Promise<void> => {
    await apiClient.post('/admin/restart', { service });
  },
};

// Discord Service
export const discordService = {
  getStatus: async (): Promise<DiscordStatus> => {
    return apiClient.get<DiscordStatus>('/discord/status');
  },

  sendMessage: async (channelId: string, message: string): Promise<void> => {
    await apiClient.post('/discord/send', { channelId, message });
  },

  getChannels: async (): Promise<string[]> => {
    return apiClient.get<string[]>('/discord/channels');
  },
};

// Activity Log Service
export const activityService = {
  getLogs: async (limit = 100): Promise<ActivityLogEntry[]> => {
    return apiClient.get<ActivityLogEntry[]>('/activity/logs', { limit });
  },

  getRecentActivity: async (): Promise<ActivityLogEntry[]> => {
    return apiClient.get<ActivityLogEntry[]>('/activity/recent');
  },
};

// Notifications Service
export const notificationService = {
  registerToken: async (token: string): Promise<void> => {
    await apiClient.post('/notifications/register', { token });
  },

  getPreferences: async (): Promise<Record<string, boolean>> => {
    return apiClient.get<Record<string, boolean>>('/notifications/preferences');
  },

  updatePreferences: async (preferences: Record<string, boolean>): Promise<void> => {
    await apiClient.put('/notifications/preferences', preferences);
  },
};

export default {
  chat: chatService,
  system: systemService,
  discord: discordService,
  activity: activityService,
  notifications: notificationService,
};