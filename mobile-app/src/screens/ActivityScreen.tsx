import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { activityService, ActivityLogEntry } from '../api/services';
import { cacheStorage } from '../utils/storage';
import { format } from 'date-fns';

const ActivityScreen = () => {
  const { theme } = useTheme();
  const [activities, setActivities] = useState<ActivityLogEntry[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<'all' | 'chat' | 'system' | 'discord'>('all');

  const mockActivities: ActivityLogEntry[] = [
    {
      id: '1',
      type: 'chat',
      description: 'User sent message: "Hello Genesis"',
      timestamp: Date.now() - 1000 * 60 * 5,
      metadata: { userId: 'user1' },
    },
    {
      id: '2',
      type: 'system',
      description: 'System health check passed',
      timestamp: Date.now() - 1000 * 60 * 10,
      metadata: { latency: 45 },
    },
    {
      id: '3',
      type: 'discord',
      description: 'Discord bot responded to /ping command',
      timestamp: Date.now() - 1000 * 60 * 15,
      metadata: { channel: 'general' },
    },
    {
      id: '4',
      type: 'command',
      description: 'Restart command executed',
      timestamp: Date.now() - 1000 * 60 * 30,
      metadata: { service: 'telegram' },
    },
    {
      id: '5',
      type: 'chat',
      description: 'AI response generated successfully',
      timestamp: Date.now() - 1000 * 60 * 45,
    },
    {
      id: '6',
      type: 'system',
      description: 'Memory cache cleared',
      timestamp: Date.now() - 1000 * 60 * 60,
    },
    {
      id: '7',
      type: 'discord',
      description: 'New member joined Discord server',
      timestamp: Date.now() - 1000 * 60 * 90,
      metadata: { member: 'JohnDoe' },
    },
    {
      id: '8',
      type: 'system',
      description: 'Backup completed successfully',
      timestamp: Date.now() - 1000 * 60 * 120,
      metadata: { size: '2.5MB' },
    },
  ];

  const fetchActivities = async () => {
    try {
      const cached = await cacheStorage.get<ActivityLogEntry[]>('activities');
      if (cached) {
        setActivities(cached);
      } else {
        setActivities(mockActivities);
      }

      try {
        const logs = await activityService.getLogs(50);
        setActivities(logs);
        await cacheStorage.set('activities', logs, 5);
      } catch (error) {
        console.log('Using mock activities');
      }
    } catch (error) {
      console.error('Error fetching activities:', error);
    }
  };

  useFocusEffect(
    useCallback(() => {
      fetchActivities();
    }, [])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchActivities();
    setRefreshing(false);
  };

  const getTypeIcon = (type: ActivityLogEntry['type']) => {
    switch (type) {
      case 'chat':
        return '💬';
      case 'system':
        return '⚙️';
      case 'discord':
        return '💜';
      case 'command':
        return '🎮';
      default:
        return '📝';
    }
  };

  const getTypeColor = (type: ActivityLogEntry['type']) => {
    switch (type) {
      case 'chat':
        return theme.primary;
      case 'system':
        return theme.secondary;
      case 'discord':
        return '#7289da';
      case 'command':
        return theme.warning;
      default:
        return theme.textSecondary;
    }
  };

  const filteredActivities = filter === 'all'
    ? activities
    : activities.filter(a => a.type === filter);

  const FilterButton = ({ type, label }: { type: typeof filter; label: string }) => (
    <TouchableOpacity
      style={[
        styles.filterButton,
        {
          backgroundColor: filter === type ? theme.primary : theme.surface,
        },
      ]}
      onPress={() => setFilter(type)}
    >
      <Text
        style={[
          styles.filterButtonText,
          { color: filter === type ? theme.background : theme.text },
        ]}
      >
        {label}
      </Text>
    </TouchableOpacity>
  );

  const renderActivity = ({ item }: { item: ActivityLogEntry }) => (
    <View style={[styles.activityItem, { backgroundColor: theme.surface }]}>
      <View style={[styles.activityIcon, { backgroundColor: getTypeColor(item.type) + '20' }]}>
        <Text style={styles.activityIconText}>{getTypeIcon(item.type)}</Text>
      </View>
      <View style={styles.activityContent}>
        <Text style={[styles.activityDescription, { color: theme.text }]}>
          {item.description}
        </Text>
        <Text style={[styles.activityTime, { color: theme.textSecondary }]}>
          {format(new Date(item.timestamp), 'MMM dd, HH:mm')}
        </Text>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <View style={styles.header}>
        <Text style={[styles.headerTitle, { color: theme.text }]}>Activity Log</Text>
        <Text style={[styles.headerSubtitle, { color: theme.textSecondary }]}>
          {activities.length} events
        </Text>
      </View>

      <View style={styles.filterContainer}>
        <FilterButton type="all" label="All" />
        <FilterButton type="chat" label="Chat" />
        <FilterButton type="system" label="System" />
        <FilterButton type="discord" label="Discord" />
      </View>

      <FlatList
        data={filteredActivities}
        renderItem={renderActivity}
        keyExtractor={item => item.id}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={theme.primary}
          />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>📋</Text>
            <Text style={[styles.emptyText, { color: theme.textSecondary }]}>
              No activities yet
            </Text>
          </View>
        }
      />
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    padding: 16,
    paddingBottom: 8,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  headerSubtitle: {
    fontSize: 14,
    marginTop: 4,
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingBottom: 16,
    gap: 8,
  },
  filterButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
  },
  filterButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  listContent: {
    padding: 16,
    paddingTop: 0,
  },
  activityItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: 12,
    borderRadius: 12,
    marginBottom: 8,
  },
  activityIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  activityIconText: {
    fontSize: 18,
  },
  activityContent: {
    flex: 1,
  },
  activityDescription: {
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 4,
  },
  activityTime: {
    fontSize: 12,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingTop: 50,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 16,
  },
});

export default ActivityScreen;