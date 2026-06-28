import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated, Easing, TouchableOpacity, Alert } from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useNavigation } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { RootStackParamList } from '../types';

// Startup timing tracker
const StartupMetrics = {
  startTime: Date.now(),
  steps: [] as { name: string; duration: number; status: 'pending' | 'done' | 'error' }[],
  
  log(name: string) {
    this.steps.push({ name, duration: 0, status: 'pending' });
    const start = Date.now();
    return () => {
      const duration = Date.now() - start;
      const step = this.steps.find(s => s.name === name);
      if (step) {
        step.duration = duration;
        step.status = 'done';
      }
      console.log(`[STARTUP] ${name}: ${duration}ms`);
    };
  },
  
  error(name: string, err: Error) {
    const step = this.steps.find(s => s.name === name);
    if (step) {
      step.status = 'error';
    }
    console.error(`[STARTUP ERROR] ${name}:`, err.message);
  },
  
  getReport() {
    const total = Date.now() - this.startTime;
    return this.steps.map(s => `${s.name}: ${s.duration}ms [${s.status}]`).join('\n') + 
           `\nTotal: ${total}ms`;
  }
};

type SplashScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Splash'>;

// Error state component
const ErrorScreen = ({ 
  message, 
  onRetry, 
  theme 
}: { 
  message: string; 
  onRetry: () => void; 
  theme: any;
}) => (
  <View style={[styles.container, { backgroundColor: theme.background }]}>
    <Text style={[styles.errorIcon]}>⚠️</Text>
    <Text style={[styles.errorTitle, { color: theme.error || '#ff4444' }]}>
      Startup Failed
    </Text>
    <Text style={[styles.errorMessage, { color: theme.textSecondary }]}>
      {message}
    </Text>
    <TouchableOpacity 
      style={[styles.retryButton, { backgroundColor: theme.primary }]}
      onPress={onRetry}
    >
      <Text style={[styles.retryText, { color: theme.background }]}>
        RETRY
      </Text>
    </TouchableOpacity>
  </View>
);

const SplashScreen = () => {
  const { theme } = useTheme();
  const { isAuthenticated } = useAuth();
  const navigation = useNavigation<SplashScreenNavigationProp>();
  
  const [error, setError] = useState<string | null>(null);
  const [loadingSteps, setLoadingSteps] = useState<string[]>([]);
  
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.8)).current;
  const rotateAnim = useRef(new Animated.Value(0)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;
  const progressAnim = useRef(new Animated.Value(0)).current;

  const updateStep = (step: string) => {
    setLoadingSteps(prev => [...prev, step]);
    Animated.timing(progressAnim, {
      toValue: loadingSteps.length + 1,
      duration: 300,
      useNativeDriver: false,
    }).start();
  };

  useEffect(() => {
    let isMounted = true;
    let timeoutId: NodeJS.Timeout;

    const initApp = async () => {
      try {
        // STARTUP SEQUENCE WITH TIMEOUT PROTECTION
        const MAX_STARTUP_TIME = 5000; // 5 second max
        
        // Start animations immediately
        updateStep('Starting UI...');
        
        const finishAnimation = StartupMetrics.log('Animation');
        Animated.parallel([
          Animated.timing(fadeAnim, {
            toValue: 1,
            duration: 800,
            useNativeDriver: true,
          }),
          Animated.spring(scaleAnim, {
            toValue: 1,
            tension: 40,
            friction: 6,
            useNativeDriver: true,
          }),
          Animated.loop(
            Animated.timing(rotateAnim, {
              toValue: 1,
              duration: 10000,
              easing: Easing.linear,
              useNativeDriver: true,
            })
          ),
          Animated.loop(
            Animated.sequence([
              Animated.timing(glowAnim, {
                toValue: 1,
                duration: 1500,
                useNativeDriver: true,
              }),
              Animated.timing(glowAnim, {
                toValue: 0,
                duration: 1500,
                useNativeDriver: true,
              }),
            ])
          ),
        ]).start();
        finishAnimation();
        updateStep('Theme loaded');

        if (!isMounted) return;

        // Theme loaded (instant for local theme)
        updateStep('Theme ready');

        // Secure storage check (with timeout)
        const storageDone = StartupMetrics.log('Secure Storage');
        try {
          await Promise.race([
            import('../utils/storage'),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('Storage timeout')), 2000)
            )
          ]);
          storageDone();
          updateStep('Storage ready');
        } catch (e: any) {
          StartupMetrics.error('Secure Storage', e);
          updateStep('Storage skipped');
        }

        if (!isMounted) return;

        // Token loading (with timeout)
        const tokenDone = StartupMetrics.log('Token Loading');
        try {
          await Promise.race([
            import('../api/client'),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('Token load timeout')), 2000)
            )
          ]);
          tokenDone();
          updateStep('Token loaded');
        } catch (e: any) {
          StartupMetrics.error('Token Loading', e);
          updateStep('Token check skipped');
        }

        if (!isMounted) return;

        // Backend health check (with timeout - NON-BLOCKING)
        const healthDone = StartupMetrics.log('Backend Health');
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 3000);
          
          await fetch(`${'https://genesis-protocol-00a1.up.railway.app'}/api/health`, {
            signal: controller.signal
          });
          
          clearTimeout(timeout);
          healthDone();
          updateStep('Backend connected');
        } catch (e: any) {
          StartupMetrics.error('Backend Health', e);
          // Don't block on backend failure - continue to app
          updateStep('Offline mode');
        }

        if (!isMounted) return;

        // Auth check (with timeout)
        const authDone = StartupMetrics.log('Auth Check');
        try {
          await Promise.race([
            new Promise(resolve => setTimeout(resolve, 500)),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('Auth timeout')), 2000)
            )
          ]);
          authDone();
          updateStep('Auth verified');
        } catch (e: any) {
          StartupMetrics.error('Auth Check', e);
          updateStep('Auth pending');
        }

        if (!isMounted) return;

        // Navigation (max 500ms)
        const navDone = StartupMetrics.log('Navigation');
        updateStep('Navigating...');
        
        setTimeout(() => {
          navDone();
          console.log('[STARTUP REPORT]\n' + StartupMetrics.getReport());
          
          if (!isMounted) return;
          
          if (isAuthenticated) {
            navigation.replace('Main');
          } else {
            navigation.replace('Login');
          }
        }, 500);

      } catch (err: any) {
        console.error('[STARTUP CRITICAL ERROR]:', err);
        if (isMounted) {
          setError(err.message || 'Unknown startup error');
        }
      }
    };

    // Set max startup timeout
    timeoutId = setTimeout(() => {
      console.log('[STARTUP] Max time exceeded, forcing navigation...');
      console.log('[STARTUP REPORT]\n' + StartupMetrics.getReport());
      if (isMounted) {
        if (isAuthenticated) {
          navigation.replace('Main');
        } else {
          navigation.replace('Login');
        }
      }
    }, MAX_STARTUP_TIME);

    initApp();

    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
    };
  }, [isAuthenticated, navigation, fadeAnim, scaleAnim, rotateAnim, glowAnim, loadingSteps.length]);

  // Show error screen if startup failed
  if (error) {
    return (
      <ErrorScreen 
        message={error} 
        onRetry={() => {
          setError(null);
          setLoadingSteps([]);
        }} 
        theme={theme}
      />
    );
  }

  const spin = rotateAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  const glowOpacity = glowAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.8],
  });

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      {/* Background grid effect */}
      <View style={styles.gridOverlay} />
      
      <Animated.View
        style={[
          styles.logoContainer,
          {
            opacity: fadeAnim,
            transform: [{ scale: scaleAnim }],
          },
        ]}
      >
        {/* Outer ring */}
        <Animated.View
          style={[
            styles.outerRing,
            { 
              borderColor: theme.primary,
              transform: [{ rotate: spin }],
              opacity: glowOpacity,
            },
          ]}
        />
        
        {/* Main logo container */}
        <View style={[styles.logoOuter, { borderColor: theme.primary }]}>
          <Animated.View 
            style={[
              styles.logoGlow, 
              { 
                backgroundColor: theme.primary,
                opacity: glowOpacity,
              }
            ]} 
          />
          <View style={[styles.logoInner, { backgroundColor: theme.primary }]}>
            <Text style={[styles.logoText, { color: theme.background }]}>G</Text>
          </View>
        </View>
        
        <Text style={[styles.title, { color: theme.text }]}>GENESIS OS</Text>
        <Text style={[styles.subtitle, { color: theme.primary }]}>
          v2.0
        </Text>
        <Text style={[styles.tagline, { color: theme.textSecondary }]}>
          OPERATING SYSTEM
        </Text>
      </Animated.View>
      
      {/* Loading indicator */}
      <Animated.View style={[styles.loadingContainer, { opacity: fadeAnim }]}>
        <View style={[styles.loadingBar, { backgroundColor: theme.border }]}>
          <Animated.View 
            style={[
              styles.loadingProgress, 
              { backgroundColor: theme.primary }
            ]} 
          />
        </View>
        <Text style={[styles.loadingText, { color: theme.textSecondary }]}>
          {loadingSteps.length > 0 ? loadingSteps[loadingSteps.length - 1] : 'INITIALIZING...'}
        </Text>
        {loadingSteps.length > 0 && (
          <View style={styles.stepsContainer}>
            {loadingSteps.slice(-3).map((step, i) => (
              <Text key={i} style={[styles.stepText, { color: theme.textSecondary, opacity: 0.5 + i * 0.2 }]}>
                • {step}
              </Text>
            ))}
          </View>
        )}
      </Animated.View>
      
      {/* Version */}
      <Text style={[styles.version, { color: theme.textSecondary }]}>
        GENESIS PROTOCOL © 2026
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  gridOverlay: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.03,
  },
  logoContainer: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  outerRing: {
    position: 'absolute',
    width: 180,
    height: 180,
    borderRadius: 90,
    borderWidth: 2,
    borderStyle: 'dashed',
  },
  logoOuter: {
    width: 140,
    height: 140,
    borderRadius: 35,
    borderWidth: 3,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
    overflow: 'hidden',
  },
  logoGlow: {
    position: 'absolute',
    width: 100,
    height: 100,
    borderRadius: 50,
  },
  logoInner: {
    width: 100,
    height: 100,
    borderRadius: 25,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoText: {
    fontSize: 56,
    fontWeight: 'bold',
    letterSpacing: 4,
  },
  title: {
    fontSize: 32,
    fontWeight: '900',
    letterSpacing: 6,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 18,
    fontWeight: '300',
    letterSpacing: 8,
    marginBottom: 12,
  },
  tagline: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 4,
  },
  loadingContainer: {
    position: 'absolute',
    bottom: 120,
    alignItems: 'center',
  },
  loadingBar: {
    width: 200,
    height: 2,
    borderRadius: 1,
    overflow: 'hidden',
    marginBottom: 12,
  },
  loadingProgress: {
    width: '60%',
    height: '100%',
    borderRadius: 1,
  },
  loadingText: {
    fontSize: 10,
    letterSpacing: 2,
    fontWeight: '500',
  },
  stepsContainer: {
    marginTop: 8,
    alignItems: 'center',
  },
  stepText: {
    fontSize: 8,
    letterSpacing: 1,
    marginVertical: 2,
  },
  version: {
    position: 'absolute',
    bottom: 40,
    fontSize: 10,
    letterSpacing: 1,
  },
  // Error screen styles
  errorIcon: {
    fontSize: 64,
    marginBottom: 24,
  },
  errorTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 12,
    letterSpacing: 2,
  },
  errorMessage: {
    fontSize: 14,
    textAlign: 'center',
    marginHorizontal: 40,
    marginBottom: 32,
    lineHeight: 20,
  },
  retryButton: {
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 8,
  },
  retryText: {
    fontSize: 14,
    fontWeight: 'bold',
    letterSpacing: 2,
  },
});

export default SplashScreen;