import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Dimensions,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { systemService } from '../api/services';
import { cacheStorage } from '../utils/storage';
import { format } from 'date-fns';

const { width } = Dimensions.get('window');

interface ServiceStatus {
  name: string;
  status: 'online' | 'offline' | 'error';
  icon: string;
  lastCheck: Date;
}

interface DashboardStats {
  totalChats: number;
  uptime: string;
  activeServices: number;
  totalServices: number;
}

const DashboardScreen = () => {
  const { theme } = useTheme();
  const { user } = useAuth();
  const [refreshing, setRefreshing] = useState(false);
  const [stats, setStats] = useState<DashboardStats>({
    totalChats: 0,
    uptime: '0h',
    activeServices: 0,
    totalServices: 3,
  });
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: 'Telegram', status: 'online', icon: '📱', lastCheck: new Date() },
    { name: 'Discord', status: 'online', icon: '💬', lastCheck: new Date() },
    { name: 'Web API', status: 'online', icon: '🌐', lastCheck: new Date() },
  ]);

  const fetchDashboardData = async () => {
    try {
      // Try to get cached data first
      const cachedStats = await cacheStorage.get<DashboardStats>('dashboard_stats');
      if (cachedStats) {
        setStats(cachedStats);
      }

      // Try to fetch fresh data
      try {
        const status = await systemService.getStatus();
        setServices([
          { name: 'Telegram', status: status.services.telegram ? 'online' : 'offline', icon: '📱', lastCheck: new Date() },
          { name: 'Discord', status: status.services.discord ? 'online' : 'offline', icon: '💬', lastCheck: new Date() },
          { name: 'Web API', status: status.services.web ? 'online' : 'offline', icon: '🌐', lastCheck: new Date() },
        ]);
        setStats({
          totalChats: 156,
          uptime: formatUptime(status.uptime),
          activeServices: Object.values(status.services).filter(Boolean).length,
          totalServices: 3,
        });
        
        // Cache the stats
        await cacheStorage.set('dashboard_stats', stats, 5);
      } catch (error) {
        console.log('Backend not available, showing cached data');
      }
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    }
  };

  const formatUptime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  useFocusEffect(
    useCallback(() => {
      fetchDashboardData();
    }, [])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchDashboardData();
    setRefreshing(false);
  };

  const getStatusColor = (status: ServiceStatus['status']) => {
    switch (status) {
      case 'online':
        return theme.success;
      case 'offline':
        return theme.textSecondary;
      case 'error':
        return theme.error;
    }
  };

  const StatCard = ({ title, value, icon }: { title: string; value: string; icon: string }) => (
    <View style={[styles.statCard, { backgroundColor: theme.surface }]}>
      <Text style={styles.statIcon}>{icon}</Text>
      <Text style={[styles.statValue, { color: theme.text }]}>{value}</Text>
      <Text style={[styles.statTitle, { color: theme.textSecondary }]}>{title}</Text>
    </View>
  );

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
          <View>
            <Text style={[styles.greeting, { color: theme.textSecondary }]}>
              Welcome back,
            </Text>
            <Text style={[styles.userName, { color: theme.text }]}>
              {user?.name || 'Operator'}
            </Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: theme.primary }]}>
            <Text style={[styles.statusBadgeText, { color: theme.background }]}>LIVE</Text>
          </View>
        </View>

        {/* System Status Overview */}
        <View style={[styles.section, { backgroundColor: theme.surface }]}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>System Status</Text>
          <View style={styles.statusRow}>
            <View style={styles.statusIndicator}>
              <View style={[styles.statusDot, { backgroundColor: theme.success }]} />
              <Text style={[styles.statusText, { color: theme.success }]}>All Systems Operational</Text>
            </View>
            <Text style={[styles.lastCheck, { color: theme.textSecondary }]}>
              Updated {format(new Date(), 'HH:mm')}
            </Text>
          </View>
        </View>

        {/* Stats Grid */}
        <View style={styles.statsGrid}>
          <StatCard title="Total Chats" value={stats.totalChats.toString()} icon="💬" />
          <StatCard title="Uptime" value={stats.uptime} icon="⏱️" />
          <StatCard title="Services" value={`${stats.activeServices}/${stats.totalServices}`} icon="🔧" />
          <StatCard title="Status" value="Active" icon="✅" />
        </View>

        {/* Services List */}
        <View style={[styles.section, { backgroundColor: theme.surface }]}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>Services</Text>
          {services.map((service, index) => (
            <TouchableOpacity
              key={service.name}
              style={[
                styles.serviceItem,
                index < services.length - 1 && { borderBottomWidth: 1, borderBottomColor: theme.border },
              ]}
            >
              <View style={styles.serviceInfo}>
                <Text style={styles.serviceIcon}>{service.icon}</Text>
                <View>
                  <Text style={[styles.serviceName, { color: theme.text }]}>{service.name}</Text>
                  <Text style={[styles.serviceStatus, { color: getStatusColor(service.status) }]}>
                    {service.status.charAt(0).toUpperCase() + service.status.slice(1)}
                  </Text>
                </View>
              </View>
              <View style={[styles.serviceDot, { backgroundColor: getStatusColor(service.status) }]} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Quick Actions */}
        <View style={styles.quickActions}>
          <Text style={[styles.sectionTitle, { color: theme.text }]}>Quick Actions</Text>
          <View style={styles.actionButtons}>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
            >
              <Text style={styles.actionIcon}>🚀</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>Restart</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
            >
              <Text style={styles.actionIcon}>📊</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>Logs</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
            >
              <Text style={styles.actionIcon}>⚙️</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>Config</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: theme.surface }]}
            >
              <Text style={styles.actionIcon}>🔔</Text>
              <Text style={[styles.actionText, { color: theme.text }]}>Alerts</Text>
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
  greeting: {
    fontSize: 14,
  },
  userName: {
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
  section: {
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  statusIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  statusText: {
    fontSize: 14,
    fontWeight: '600',
  },
  lastCheck: {
    fontSize: 12,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  statCard: {
    width: (width - 48) / 2,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    alignItems: 'center',
  },
  statIcon: {
    fontSize: 28,
    marginBottom: 8,
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 4,
  },
  statTitle: {
    fontSize: 12,
  },
  serviceItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  serviceInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  serviceIcon: {
    fontSize: 24,
    marginRight: 12,
  },
  serviceName: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 2,
  },
  serviceStatus: {
    fontSize: 12,
  },
  serviceDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  quickActions: {
    marginBottom: 16,
  },
  actionButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  actionButton: {
    width: (width - 64) / 4,
    borderRadius: 12,
    padding: 12,
    alignItems: 'center',
  },
  actionIcon: {
    fontSize: 24,
    marginBottom: 4,
  },
  actionText: {
    fontSize: 11,
    fontWeight: '600',
  },
});

export default DashboardScreen;