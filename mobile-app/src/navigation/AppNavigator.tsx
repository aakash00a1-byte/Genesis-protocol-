import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { RootStackParamList, MainTabParamList } from '../types';

// Screens
import SplashScreen from '../screens/SplashScreen';
import LoginScreen from '../screens/LoginScreen';
import RegisterScreen from '../screens/RegisterScreen';
import DashboardScreen from '../screens/DashboardScreen';
import ChatScreen from '../screens/ChatScreen';
import ActivityScreen from '../screens/ActivityScreen';
import DiscordScreen from '../screens/DiscordScreen';
import SettingsScreen from '../screens/SettingsScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

const MainTabs = () => {
  const { theme } = useTheme();

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: theme.surface,
          borderTopColor: theme.border,
          borderTopWidth: 1,
          paddingBottom: 8,
          paddingTop: 8,
          height: 60,
        },
        tabBarActiveTintColor: theme.primary,
        tabBarInactiveTintColor: theme.textSecondary,
        tabBarLabelStyle: {
          fontSize: 12,
          fontWeight: '600',
        },
      }}
    >
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{
          tabBarLabel: 'Dashboard',
          tabBarIcon: ({ color, size }) => (
            <View style={[styles.iconContainer, { borderColor: color }]}>
              <View style={[styles.dashboardIcon, { backgroundColor: color }]} />
            </View>
          ),
        }}
      />
      <Tab.Screen
        name="Chat"
        component={ChatScreen}
        options={{
          tabBarLabel: 'Chat',
          tabBarIcon: ({ color }) => (
            <View style={[styles.iconContainer, { borderColor: color }]}>
              <View style={[styles.chatIcon, { borderColor: color }]} />
            </View>
          ),
        }}
      />
      <Tab.Screen
        name="Activity"
        component={ActivityScreen}
        options={{
          tabBarLabel: 'Activity',
          tabBarIcon: ({ color }) => (
            <View style={[styles.iconContainer, { borderColor: color }]}>
              <View style={[styles.activityIcon, { backgroundColor: color }]} />
            </View>
          ),
        }}
      />
      <Tab.Screen
        name="Discord"
        component={DiscordScreen}
        options={{
          tabBarLabel: 'Discord',
          tabBarIcon: ({ color }) => (
            <View style={[styles.iconContainer, { borderColor: color }]}>
              <View style={[styles.discordIcon, { borderColor: color }]} />
            </View>
          ),
        }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          tabBarLabel: 'Settings',
          tabBarIcon: ({ color }) => (
            <View style={[styles.iconContainer, { borderColor: color }]}>
              <View style={[styles.settingsIcon, { borderColor: color }]} />
            </View>
          ),
        }}
      />
    </Tab.Navigator>
  );
};

const AppNavigator = () => {
  const { isLoading, isAuthenticated } = useAuth();
  const { theme } = useTheme();

  if (isLoading) {
    return (
      <View style={[styles.loadingContainer, { backgroundColor: theme.background }]}>
        <ActivityIndicator size="large" color={theme.primary} />
      </View>
    );
  }

  return (
    <Stack.Navigator
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: theme.background },
        animation: 'fade',
      }}
    >
      {!isAuthenticated ? (
        <>
          <Stack.Screen name="Splash" component={SplashScreen} />
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="Register" component={RegisterScreen} />
        </>
      ) : (
        <>
          <Stack.Screen name="Main" component={MainTabs} />
        </>
      )}
    </Stack.Navigator>
  );
};

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  iconContainer: {
    width: 24,
    height: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  dashboardIcon: {
    width: 16,
    height: 16,
    borderRadius: 4,
  },
  chatIcon: {
    width: 16,
    height: 16,
    borderWidth: 2,
    borderRadius: 8,
  },
  activityIcon: {
    width: 14,
    height: 14,
    borderRadius: 7,
  },
  discordIcon: {
    width: 18,
    height: 14,
    borderWidth: 2,
    borderRadius: 4,
  },
  settingsIcon: {
    width: 16,
    height: 16,
    borderWidth: 2,
    borderRadius: 8,
  },
});

export default AppNavigator;