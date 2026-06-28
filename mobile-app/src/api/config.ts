// Genesis Protocol API Configuration
// Railway Backend URL - Update this to your deployed Railway URL
export const API_CONFIG = {
  BASE_URL: 'https://genesis-protocol-00a1.up.railway.app',
  API_VERSION: '',  // Backend uses /api/ prefix directly
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
};

export const getFullApiUrl = (endpoint: string): string => {
  return `${API_CONFIG.BASE_URL}/api/${endpoint}`;
};