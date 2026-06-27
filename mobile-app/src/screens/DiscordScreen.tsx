import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { discordService, DiscordStatus } from '../api/services';
import { format } from 'date-fns';

const DiscordScreen = () => {
  const { theme } = useTheme();
  const [refreshing, setRefreshing] = useState(false);
  const [discordStatus, setDiscordStatus] = useState<DiscordStatus>({
    connected: true,
    serverName: 'Genesis Board',
    channelCount: 5,
    lastActivity: Date.now(),
  });

  const mockChannels = [
    { id: '1', name: 'general', type: 'text' },
    { id: '2', name: 'commands', type: 'text' },
    { id: '3', name: 'bot-logs', type: 'text' },
    { id: '4', name: 'general', type: 'voice' },
  ];

  const [channels] = useState(mockChannels);

  const fetchDiscordStatus = async () => {
    try {
      try {
        const status = await discordService.getStatus();
        setDiscordStatus(status);
      } catch (error) {
        console.log('Using mock Discord status');
      }
    } catch (error) {
      console.error('Error fetching Discord status:', error);
    }
  };

  useFocusEffect(
    useCallback(() => {
      fetchDiscordStatus();
    }, [])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchDiscordStatus();
    setRefreshing(false);
  };

  const handleChannelPress = (channel: typeof channels[0]) => {
    Alert.alert(
      channel.name,
      `This would send a message to #${channel.name} through the Discord bot.`,
      [{ text: 'OK' }]
    );
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={theme.primary}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={[styles.headerTitle, { color: theme.text }]}>Discord</Text>
          <View style={[styles.statusBadge, { backgroundColor: discordStatus.connected ? theme.success : theme.error }]}>
            <Text style={[styles.statusBadgeText, { color: '#ffffff' }]}>
              {discordStatus.connected ? 'Connected' : 'Disconnected'}
            </Text>
          </View>
        </View>

        {/* Server Card */}
        <View style={[styles.serverCard, { backgroundColor: theme.surface }]}>
          <View style={styles.serverHeader}>
            <View style={[styles.serverIcon, { backgroundColor: '#7289da' }]}>
              <Text style={styles.serverIconText}>G</Text>
            </View>
            <View style={styles.serverInfo}>
              <Text style={[styles.serverName, { color: theme.text }]}>
                {discordStatus.serverName}
              </Text>
              <Text style={[styles.serverStats, { color: theme.textSecondary }]}>
                {discordStatus.channelCount} channels
              </Text>
            </View>
          </View>
          <Text style={[styles.lastActivity, { color: theme.textSecondary }]}>
            Last activity: {format(new Date(discordStatus.lastActivity), 'MMM dd, HH:mm')}
          </Text>
        </View>

        {/* Quick Stats */}
        <View style={styles.statsRow}>
          <View style={[styles.statCard, { backgroundColor: theme.surface }]}>
            <Text style={styles.statIcon}>👥</Text>
            <Text style={[styles.statValue, { color: theme.text }]}>24</Text>
            <Text style={[styles.statLabel, { color: theme.textSecondary }]}>Members</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: theme.surface }]}>
            <Text style={styles.statIcon}>💬</Text>
            <Text style={[styles.statValue, { color: theme.text }]}>156</Text>
            <Text style={[styles.statLabel, { color: theme.textSecondary }]}>Messages</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: theme.surface }]}>
            <Text style={styles.statIcon}>⚡</Text>
            <Text style={[styles.statValue, { color: theme.text }]}>89</Text>
            <Text style={[styles.statLabel, { color: theme.textSecondary }]}>Commands</Text>
          </View>
        </View>

        {/* Channels */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>Channels</Text>
          {channels.map((channel) => (
            <TouchableOpacity
              key={channel.id}
              style={[styles.channelItem, { backgroundColor: theme.surface }]}
              onPress={() => handleChannelPress(channel)}
            >
              <View style={styles.channelInfo}>
                <Text style={styles.channelIcon}>
                  {channel.type === 'voice' ? '🔊' : '#'}
                </Text>
                <Text style={[styles.channelName, { color: theme.text }]}>
                  {channel.name}
                </Text>
              </View>
              <Text style={[styles.channelType, { color: theme.textSecondary }]}>
                {channel.type}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Quick Actions */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>Quick Actions</Text>
          <View style={styles.actionGrid}>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
              onPress={() => Alert.alert('Broadcast', 'Send message to all channels')}
            >
              <Text style={styles.actionIcon}>📢</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>Broadcast</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
              onPress={() => Alert.alert('Logs', 'View Discord bot logs')}
            >
              <Text style={styles.actionIcon}>📊</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>View Logs</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
              onPress={() => Alert.alert('Settings', 'Discord settings')}
            >
              <Text style={styles.actionIcon}>⚙️</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>Settings</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
              onPress={() => Alert.alert('Help', 'Available commands')}
            >
              <Text style={styles.actionIcon}>❓</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>Commands</Text>
            </TouchableOpacity>
          </View>
        </View>
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
  },
  statusBadgeText: {
    fontSize: 12,
    fontWeight: 'bold',
  },
  serverCard: {
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  serverHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  serverIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  serverIconText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#ffffff',
  },
  serverInfo: {
    flex: 1,
  },
  serverName: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 2,
  },
  serverStats: {
    fontSize: 14,
  },
  lastActivity: {
    fontSize: 12,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  statCard: {
    flex: 1,
    borderRadius: 12,
    padding: 12,
    alignItems: 'center',
    marginHorizontal: 4,
  },
  statIcon: {
    fontSize: 24,
    marginBottom: 4,
  },
  statValue: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 2,
  },
  statLabel: {
    fontSize: 11,
  },
  section: {
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  channelItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    marginBottom: 8,
  },
  channelInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  channelIcon: {
    fontSize: 18,
    marginRight: 12,
    color: '#7289da',
    fontWeight: 'bold',
  },
  channelName: {
    fontSize: 16,
  },
  channelType: {
    fontSize: 12,
    textTransform: 'capitalize',
  },
  actionGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  actionButton: {
    width: '48%',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  actionIcon: {
    fontSize: 28,
    marginBottom: 8,
  },
  actionText: {
    fontSize: 14,
    fontWeight: '600',
  },
});

export default DiscordScreen;