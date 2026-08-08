import React, { useEffect, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, Animated, Easing, TouchableOpacity } from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { RootStackParamList } from '../types';

type SplashScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Splash'>;

const SplashScreen = () => {
  const { theme } = useTheme();
  const { isAuthenticated } = useAuth();
  const navigation = useNavigation<SplashScreenNavigationProp>();
  const hasNavigated = useRef(false);
  
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.8)).current;
  const rotateAnim = useRef(new Animated.Value(0)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;
  const progressAnim = useRef(new Animated.Value(0)).current;
  const statusText = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (hasNavigated.current) return;
    hasNavigated.current = true;

    // Start animations immediately
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 600,
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

    // Navigate after 2.5 seconds max
    const timer = setTimeout(() => {
      if (isAuthenticated) {
        navigation.reset({
          index: 0,
          routes: [{ name: 'Main' }],
        });
      } else {
        navigation.reset({
          index: 0,
          routes: [{ name: 'Login' }],
        });
      }
    }, 2500);

    return () => clearTimeout(timer);
  }, [isAuthenticated, navigation, fadeAnim, scaleAnim]);

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
        <Text style={[styles.subtitle, { color: theme.primary }]}>v2.0</Text>
        <Text style={[styles.tagline, { color: theme.textSecondary }]}>OPERATING SYSTEM</Text>
      </Animated.View>
      
      <Animated.View style={[styles.loadingContainer, { opacity: fadeAnim }]}>
        <View style={[styles.loadingBar, { backgroundColor: theme.border }]}>
          <Animated.View 
            style={[styles.loadingProgress, { backgroundColor: theme.primary }]} 
          />
        </View>
        <Text style={[styles.loadingText, { color: theme.textSecondary }]}>
          INITIALIZING...
        </Text>
      </Animated.View>
      
      <Text style={[styles.version, { color: theme.textSecondary }]}>GENESIS PROTOCOL © 2026</Text>
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
  version: {
    position: 'absolute',
    bottom: 40,
    fontSize: 10,
    letterSpacing: 1,
  },
});

export default SplashScreen;