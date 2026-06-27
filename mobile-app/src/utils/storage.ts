import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { CachedData, OfflineQueue } from '../types';

const SECURE_KEYS = {
  AUTH_TOKEN: 'auth_token',
  REFRESH_TOKEN: 'refresh_token',
  USER_CREDENTIALS: 'user_credentials',
  API_KEYS: 'api_keys',
};

const CACHE_PREFIX = 'cache_';
const OFFLINE_QUEUE_KEY = 'offline_queue';

// Secure Storage - for sensitive data
export const secureStorage = {
  async set(key: string, value: string): Promise<void> {
    await SecureStore.setItemAsync(key, value);
  },

  async get(key: string): Promise<string | null> {
    return SecureStore.getItemAsync(key);
  },

  async delete(key: string): Promise<void> {
    await SecureStore.deleteItemAsync(key);
  },

  async setAuthToken(token: string): Promise<void> {
    await this.set(SECURE_KEYS.AUTH_TOKEN, token);
  },

  async getAuthToken(): Promise<string | null> {
    return this.get(SECURE_KEYS.AUTH_TOKEN);
  },

  async clearAuth(): Promise<void> {
    await this.delete(SECURE_KEYS.AUTH_TOKEN);
    await this.delete(SECURE_KEYS.REFRESH_TOKEN);
  },

  async storeApiKey(provider: string, key: string): Promise<void> {
    const existingKeys = await this.getApiKeys();
    existingKeys[provider] = key;
    await this.set(SECURE_KEYS.API_KEYS, JSON.stringify(existingKeys));
  },

  async getApiKeys(): Promise<Record<string, string>> {
    const keys = await this.get(SECURE_KEYS.API_KEYS);
    return keys ? JSON.parse(keys) : {};
  },

  async getApiKey(provider: string): Promise<string | null> {
    const keys = await this.getApiKeys();
    return keys[provider] || null;
  },
};

// AsyncStorage - for non-sensitive cached data
export const cacheStorage = {
  async set<T>(key: string, data: T, ttlMinutes = 60): Promise<void> {
    const cachedData: CachedData<T> = {
      data,
      timestamp: Date.now(),
      expiresAt: Date.now() + ttlMinutes * 60 * 1000,
    };
    await AsyncStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(cachedData));
  },

  async get<T>(key: string): Promise<T | null> {
    const stored = await AsyncStorage.getItem(`${CACHE_PREFIX}${key}`);
    if (!stored) return null;

    const cachedData: CachedData<T> = JSON.parse(stored);
    
    if (Date.now() > cachedData.expiresAt) {
      await AsyncStorage.removeItem(`${CACHE_PREFIX}${key}`);
      return null;
    }

    return cachedData.data;
  },

  async remove(key: string): Promise<void> {
    await AsyncStorage.removeItem(`${CACHE_PREFIX}${key}`);
  },

  async clear(): Promise<void> {
    const keys = await AsyncStorage.getAllKeys();
    const cacheKeys = keys.filter(k => k.startsWith(CACHE_PREFIX));
    await AsyncStorage.multiRemove(cacheKeys);
  },
};

// Offline Queue Management
export const offlineQueue = {
  async add(action: OfflineQueue): Promise<void> {
    const queue = await this.getAll();
    queue.push(action);
    await AsyncStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
  },

  async getAll(): Promise<OfflineQueue[]> {
    const stored = await AsyncStorage.getItem(OFFLINE_QUEUE_KEY);
    return stored ? JSON.parse(stored) : [];
  },

  async remove(id: string): Promise<void> {
    const queue = await this.getAll();
    const filtered = queue.filter(item => item.id !== id);
    await AsyncStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(filtered));
  },

  async clear(): Promise<void> {
    await AsyncStorage.removeItem(OFFLINE_QUEUE_KEY);
  },

  async processQueue(): Promise<void> {
    const queue = await this.getAll();
    // Process queue items when back online
    // This would be called by a sync manager
  },
};

// Generate unique ID for offline queue
export const generateId = async (): Promise<string> => {
  const randomBytes = await Crypto.getRandomBytesAsync(16);
  return Array.from(randomBytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
};

export default {
  secure: secureStorage,
  cache: cacheStorage,
  offline: offlineQueue,
};