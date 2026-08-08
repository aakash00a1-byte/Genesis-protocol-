// Navigation Types
export type RootStackParamList = {
  Splash: undefined;
  Auth: undefined;
  Login: undefined;
  Register: undefined;
  Main: undefined;
  Chat: undefined;
  Settings: undefined;
  ActivityLog: undefined;
  DiscordChannels: undefined;
};

export type MainTabParamList = {
  Dashboard: undefined;
  Chat: undefined;
  Activity: undefined;
  Discord: undefined;
  Settings: undefined;
};

// User Types
export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: number;
}

// Auth Types
export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData extends LoginCredentials {
  name: string;
  confirmPassword: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

// Dashboard Types
export interface DashboardStats {
  totalChats: number;
  totalCommands: number;
  uptime: string;
  activeServices: number;
  totalServices: number;
}

// Notification Types
export interface NotificationPreferences {
  chatMessages: boolean;
  systemAlerts: boolean;
  discordMentions: boolean;
  activityUpdates: boolean;
}

// Theme Types - Genesis OS v2
export interface ThemeColors {
  primary: string;
  secondary: string;
  background: string;
  surface: string;
  text: string;
  textSecondary: string;
  error: string;
  success: string;
  warning: string;
  border: string;
  card: string;
  accent: string;
  glow: string;
}

export type ThemeMode = 'dark' | 'light';

// Offline Types
export interface CachedData<T> {
  data: T;
  timestamp: number;
  expiresAt: number;
}

export interface OfflineQueue {
  id: string;
  action: 'create' | 'update' | 'delete';
  endpoint: string;
  data: any;
  timestamp: number;
}