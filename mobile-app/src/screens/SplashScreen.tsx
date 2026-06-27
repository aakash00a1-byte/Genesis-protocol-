import React, { useEffect } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useNavigation } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { RootStackParamList } from '../types';

type SplashScreenNavigationProp = NativeStackNavigationProp<RootStackParamList, 'Splash'>;

const SplashScreen = () => {
  const { theme } = useTheme();
  const { isAuthenticated } = useAuth();
  const navigation = useNavigation<SplashScreenNavigationProp>();
  
  const fadeAnim = new Animated.Value(0);
  const scaleAnim = new Animated.Value(0.8);

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 1000,
        useNativeDriver: true,
      }),
      Animated.spring(scaleAnim, {
        toValue: 1,
        tension: 50,
        friction: 7,
        useNativeDriver: true,
      }),
    ]).start(() => {
      setTimeout(() => {
        if (isAuthenticated) {
          navigation.replace('Main');
        } else {
          navigation.replace('Login');
        }
      }, 1500);
    });
  }, [isAuthenticated, navigation]);

  return (
    <View style={[styles.container, { backgroundColor: theme.background }]}>
      <Animated.View
        style={[
          styles.logoContainer,
          {
            opacity: fadeAnim,
            transform: [{ scale: scaleAnim }],
          },
        ]}
      >
        <View style={[styles.logoOuter, { borderColor: theme.primary }]}>
          <View style={[styles.logoInner, { backgroundColor: theme.primary }]}>
            <Text style={[styles.logoText, { color: theme.background }]}>G</Text>
          </View>
        </View>
        <Text style={[styles.title, { color: theme.text }]}>Genesis Protocol</Text>
        <Text style={[styles.subtitle, { color: theme.textSecondary }]}>
          Autonomous AI Agent
        </Text>
      </Animated.View>
      
      <Animated.View style={[styles.loadingContainer, { opacity: fadeAnim }]}>
        <View style={[styles.loadingDot, { backgroundColor: theme.primary }]} />
        <View style={[styles.loadingDot, { backgroundColor: theme.primary }]} />
        <View style={[styles.loadingDot, { backgroundColor: theme.primary }]} />
      </Animated.View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoContainer: {
    alignItems: 'center',
  },
  logoOuter: {
    width: 120,
    height: 120,
    borderRadius: 30,
    borderWidth: 3,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  logoInner: {
    width: 100,
    height: 100,
    borderRadius: 25,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoText: {
    fontSize: 48,
    fontWeight: 'bold',
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    letterSpacing: 2,
  },
  loadingContainer: {
    flexDirection: 'row',
    position: 'absolute',
    bottom: 100,
  },
  loadingDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginHorizontal: 4,
    opacity: 0.5,
  },
});

export default SplashScreen;