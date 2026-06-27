import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as LocalAuthentication from 'expo-local-authentication';
import apiClient from '../api/client';
import { secureStorage } from '../utils/storage';
import { User } from '../types';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<boolean>;
  useBiometrics: boolean;
  setUseBiometrics: (value: boolean) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [useBiometrics, setUseBiometricsState] = useState(false);

  useEffect(() => {
    checkAuth();
    loadBiometricsPreference();
  }, []);

  const loadBiometricsPreference = async () => {
    const preference = await secureStorage.get('use_biometrics');
    setUseBiometricsState(preference === 'true');
  };

  const setUseBiometrics = async (value: boolean) => {
    setUseBiometricsState(value);
    await secureStorage.set('use_biometrics', value.toString());
  };

  const checkAuth = async (): Promise<boolean> => {
    setIsLoading(true);
    try {
      const token = await apiClient.getToken();
      if (token) {
        // Verify token is still valid
        setUser({ id: 'user', email: '', name: '', createdAt: Date.now() });
        return true;
      }
      setUser(null);
      return false;
    } catch (error) {
      setUser(null);
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (email: string, password: string): Promise<void> => {
    try {
      // For demo purposes, simulate login
      // In production, this would call the backend API
      const mockToken = `genesis_${Date.now()}`;
      await apiClient.setToken(mockToken);
      await secureStorage.storeApiKey('user_email', email);
      
      setUser({
        id: '1',
        email,
        name: email.split('@')[0],
        createdAt: Date.now(),
      });
    } catch (error) {
      throw new Error('Login failed. Please check your credentials.');
    }
  };

  const register = async (name: string, email: string, password: string): Promise<void> => {
    try {
      // For demo purposes, simulate registration
      // In production, this would call the backend API
      const mockToken = `genesis_${Date.now()}`;
      await apiClient.setToken(mockToken);
      
      setUser({
        id: '1',
        email,
        name,
        createdAt: Date.now(),
      });
    } catch (error) {
      throw new Error('Registration failed. Please try again.');
    }
  };

  const logout = async (): Promise<void> => {
    await apiClient.clearToken();
    await secureStorage.clearAuth();
    setUser(null);
  };

  const authenticateWithBiometrics = async (): Promise<boolean> => {
    const hasHardware = await LocalAuthentication.hasHardwareAsync();
    if (!hasHardware) return false;

    const isEnrolled = await LocalAuthentication.isEnrolledAsync();
    if (!isEnrolled) return false;

    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: 'Authenticate to access Genesis Protocol',
      cancelLabel: 'Use Password',
      disableDeviceFallback: false,
    });

    return result.success;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        checkAuth,
        useBiometrics,
        setUseBiometrics,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};