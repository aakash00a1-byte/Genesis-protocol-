// Genesis Protocol API Configuration
// Railway Backend URL - From environment variables (SECURE)

const RAILWAY_URL = process.env.EXPO_PUBLIC_RAILWAY_URL || 'https://genesis-protocol-00a1.up.railway.app';
const API_KEY = process.env.EXPO_PUBLIC_API_KEY || '';

export const API_CONFIG = {
  BASE_URL: RAILWAY_URL,
  API_VERSION: '',
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
};

export const getFullApiUrl = (endpoint: string): string => {
  return `${API_CONFIG.BASE_URL}/api/${endpoint}`;
};