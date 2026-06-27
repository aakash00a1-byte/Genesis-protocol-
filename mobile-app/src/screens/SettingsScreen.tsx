import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { secureStorage } from '../utils/storage';

const SettingsScreen = () => {
  const { theme, isDark, toggleTheme } = useTheme();
  const { logout, user, useBiometrics, setUseBiometrics } = useAuth();
  
  const [notifications, setNotifications] = useState({
    chatMessages: true,
    systemAlerts: true,
    discordMentions: false,
  });

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await logout();
          },
        },
      ]
    );
  };

  const handleBiometricsToggle = async (value: boolean) => {
    await setUseBiometrics(value);
  };

  const SettingItem = ({
    icon,
    title,
    subtitle,
    onPress,
    rightElement,
  }: {
    icon: string;
    title: string;
    subtitle?: string;
    onPress?: () => void;
    rightElement?: React.ReactNode;
  }) => (
    <TouchableOpacity
      style={[styles.settingItem, { backgroundColor: theme.surface }]}
      onPress={onPress}
      disabled={!onPress}
    >
      <View style={styles.settingLeft}>
        <Text style={styles.settingIcon}>{icon}</Text>
        <View style={styles.settingText}>
          <Text style={[styles.settingTitle, { color: theme.text }]}>{title}</Text>
          {subtitle && (
            <Text style={[styles.settingSubtitle, { color: theme.textSecondary }]}>
              {subtitle}
            </Text>
          )}
        </View>
      </View>
      {rightElement}
    </TouchableOpacity>
  );

  const SectionHeader = ({ title }: { title: string }) => (
    <Text style={[styles.sectionHeader, { color: theme.textSecondary }]}>{title}</Text>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={[styles.headerTitle, { color: theme.text }]}>Settings</Text>
        </View>

        {/* Profile Section */}
        <SectionHeader title="ACCOUNT" />
        <View style={[styles.profileCard, { backgroundColor: theme.surface }]}>
          <View style={[styles.avatar, { backgroundColor: theme.primary }]}>
            <Text style={[styles.avatarText, { color: theme.background }]}>
              {(user?.name || 'U')[0].toUpperCase()}
            </Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={[styles.profileName, { color: theme.text }]}>
              {user?.name || 'User'}
            </Text>
            <Text style={[styles.profileEmail, { color: theme.textSecondary }]}>
              {user?.email || 'user@example.com'}
            </Text>
          </View>
        </View>

        {/* Security Section */}
        <SectionHeader title="SECURITY" />
        <SettingItem
          icon="🔐"
          title="Biometric Login"
          subtitle="Use fingerprint or face ID"
          rightElement={
            <Switch
              value={useBiometrics}
              onValueChange={handleBiometricsToggle}
              trackColor={{ false: theme.border, true: theme.primary }}
              thumbColor="#ffffff"
            />
          }
        />
        <SettingItem
          icon="🔑"
          title="Change Password"
          subtitle="Update your password"
          onPress={() => Alert.alert('Change Password', 'Password change would be handled here')}
        />
        <SettingItem
          icon="🔑"
          title="API Keys"
          subtitle="Manage API keys"
          onPress={() => Alert.alert('API Keys', 'API key management would be handled here')}
        />

        {/* Appearance Section */}
        <SectionHeader title="APPEARANCE" />
        <SettingItem
          icon={isDark ? '🌙' : '☀️'}
          title="Dark Mode"
          subtitle={isDark ? 'Dark theme enabled' : 'Light theme enabled'}
          rightElement={
            <Switch
              value={isDark}
              onValueChange={toggleTheme}
              trackColor={{ false: theme.border, true: theme.primary }}
              thumbColor="#ffffff"
            />
          }
        />

        {/* Notifications Section */}
        <SectionHeader title="NOTIFICATIONS" />
        <SettingItem
          icon="💬"
          title="Chat Messages"
          subtitle="Get notified for new messages"
          rightElement={
            <Switch
              value={notifications.chatMessages}
              onValueChange={(v) => setNotifications(prev => ({ ...prev, chatMessages: v }))}
              trackColor={{ false: theme.border, true: theme.primary }}
              thumbColor="#ffffff"
            />
          }
        />
        <SettingItem
          icon="⚠️"
          title="System Alerts"
          subtitle="Critical system notifications"
          rightElement={
            <Switch
              value={notifications.systemAlerts}
              onValueChange={(v) => setNotifications(prev => ({ ...prev, systemAlerts: v }))}
              trackColor={{ false: theme.border, true: theme.primary }}
              thumbColor="#ffffff"
            />
          }
        />
        <SettingItem
          icon="💜"
          title="Discord Mentions"
          subtitle="When someone mentions you"
          rightElement={
            <Switch
              value={notifications.discordMentions}
              onValueChange={(v) => setNotifications(prev => ({ ...prev, discordMentions: v }))}
              trackColor={{ false: theme.border, true: theme.primary }}
              thumbColor="#ffffff"
            />
          }
        />

        {/* Connection Section */}
        <SectionHeader title="CONNECTION" />
        <SettingItem
          icon="🌐"
          title="Backend URL"
          subtitle="https://genesis-protocol-00a1.up.railway.app"
          onPress={() => Alert.alert('Backend URL', 'Railway backend URL configuration')}
        />
        <SettingItem
          icon="🔄"
          title="Reconnect"
          subtitle="Force reconnect to backend"
          onPress={() => Alert.alert('Reconnect', 'Attempting to reconnect...')}
        />

        {/* Data Section */}
        <SectionHeader title="DATA" />
        <SettingItem
          icon="💾"
          title="Clear Cache"
          subtitle="Free up storage space"
          onPress={() => Alert.alert('Clear Cache', 'Cache cleared successfully')}
        />
        <SettingItem
          icon="📤"
          title="Export Data"
          subtitle="Download your data"
          onPress={() => Alert.alert('Export Data', 'Data export would be handled here')}
        />

        {/* About Section */}
        <SectionHeader title="ABOUT" />
        <SettingItem
          icon="ℹ️"
          title="Version"
          subtitle="1.0.0"
        />
        <SettingItem
          icon="📖"
          title="Documentation"
          onPress={() => Alert.alert('Documentation', 'Opening documentation...')}
        />
        <SettingItem
          icon="🐛"
          title="Report Bug"
          onPress={() => Alert.alert('Report Bug', 'Bug reporting would be handled here')}
        />

        {/* Logout */}
        <TouchableOpacity
          style={[styles.logoutButton, { backgroundColor: theme.error + '20' }]}
          onPress={handleLogout}
        >
          <Text style={[styles.logoutText, { color: theme.error }]}>Logout</Text>
        </TouchableOpacity>

        {/* Footer */}
        <Text style={[styles.footer, { color: theme.textSecondary }]}>
          Genesis Protocol v1.0.0{'\n'}
          Built with ❤️ for autonomous AI
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
  },
  header: {
    marginBottom: 24,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  sectionHeader: {
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 1,
    marginTop: 24,
    marginBottom: 12,
    marginLeft: 4,
  },
  profileCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 16,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  avatarText: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  profileInfo: {
    flex: 1,
  },
  profileName: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 2,
  },
  profileEmail: {
    fontSize: 14,
  },
  settingItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    marginBottom: 8,
  },
  settingLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  settingIcon: {
    fontSize: 24,
    marginRight: 12,
  },
  settingText: {
    flex: 1,
  },
  settingTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 2,
  },
  settingSubtitle: {
    fontSize: 12,
  },
  logoutButton: {
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 32,
  },
  logoutText: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  footer: {
    textAlign: 'center',
    fontSize: 12,
    marginTop: 32,
    marginBottom: 32,
    lineHeight: 18,
  },
});

export default SettingsScreen;