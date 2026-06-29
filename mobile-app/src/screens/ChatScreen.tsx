import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Animated,
  Easing,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../context/ThemeContext';
import { chatService, ChatMessage } from '../api/services';
import { cacheStorage } from '../utils/storage';

const TYPING_SPEED = 30;

const TerminalMessage = ({ message, isUser }: { message: ChatMessage; isUser: boolean }) => {
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(!isUser);
  const [showCursor, setShowCursor] = useState(true);
  const cursorAnim = useRef(new Animated.Value(1)).current;
  
  useEffect(() => {
    if (!isUser && message.content) {
      setDisplayedText('');
      let index = 0;
      const interval = setInterval(() => {
        if (index < message.content.length) {
          setDisplayedText(message.content.substring(0, index + 1));
          index++;
        } else {
          clearInterval(interval);
          setIsTyping(false);
        }
      }, TYPING_SPEED);
      return () => clearInterval(interval);
    } else {
      setDisplayedText(message.content);
    }
  }, [message.content, isUser]);

  useEffect(() => {
    if (isTyping) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(cursorAnim, { toValue: 0, duration: 500, useNativeDriver: true }),
          Animated.timing(cursorAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
        ])
      ).start();
    }
    return () => cursorAnim.stop();
  }, [isTyping]);

  const cursorOpacity = cursorAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 1],
  });

  return (
    <View style={[styles.messageRow, isUser ? styles.userRow : styles.genesisRow]}>
      <Text style={styles.prompt}>{isUser ? '>' : 'Ω'}</Text>
      <View style={[styles.messageBox, isUser ? styles.userBox : styles.genesisBox]}>
        <Text style={[styles.messageText, { color: isUser ? '#00ff88' : '#ffffff' }]}>
          {displayedText}
        </Text>
        {isTyping && (
          <Animated.Text style={[styles.cursor, { opacity: cursorOpacity }]}>█</Animated.Text>
        )}
      </View>
    </View>
  );
};

const LoadingDots = () => {
  const dots = useRef([new Animated.Value(0), new Animated.Value(0), new Animated.Value(0)]).current;
  
  useEffect(() => {
    dots.forEach((dot, i) => {
      Animated.loop(
        Animated.sequence([
          Animated.timing(dot, { toValue: 1, duration: 300, delay: i * 150, useNativeDriver: true }),
          Animated.timing(dot, { toValue: 0, duration: 300, useNativeDriver: true }),
        ])
      ).start();
    });
  }, []);

  return (
    <View style={styles.loadingRow}>
      <Text style={styles.prompt}>Ω</Text>
      <View style={styles.genesisBox}>
        <Text style={styles.loadingText}>
          Processing
          {dots.map((dot, i) => (
            <Animated.Text key={i} style={{ opacity: dot }}>.</Animated.Text>
          ))}
        </Text>
      </View>
    </View>
  );
};

const ChatScreen = () => {
  const { theme } = useTheme();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'online' | 'offline' | 'connecting'>('connecting');
  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    loadChatHistory();
    checkConnection();
  }, []);

  const checkConnection = async () => {
    try {
      setConnectionStatus('connecting');
      await chatService.checkHealth();
      setConnectionStatus('online');
    } catch (error) {
      setConnectionStatus('offline');
    }
  };

  const loadChatHistory = async () => {
    try {
      const cached = await cacheStorage.get<ChatMessage[]>('chat_history');
      if (cached) setMessages(cached);
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  };

  const sendMessage = async () => {
    if (!inputText.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputText.trim(),
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputText('');
    setIsLoading(true);

    try {
      const response = await chatService.sendMessage(userMessage.content);
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.response || response.message || 'System offline.',
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, assistantMessage]);
      await cacheStorage.set('chat_history', [...messages, userMessage, assistantMessage], 60);
    } catch (error: any) {
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `⚠️ Error: ${error?.message || 'Connection failed. Retry.'}`,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    cacheStorage.remove('chat_history');
  };

  const statusColor = connectionStatus === 'online' ? '#00ff88' : connectionStatus === 'offline' ? '#ff4444' : '#ffaa00';
  const statusText = connectionStatus === 'online' ? 'ONLINE' : connectionStatus === 'offline' ? 'OFFLINE' : 'CONNECTING...';

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.title}>GENESIS</Text>
          <Text style={styles.subtitle}>PROTOCOL</Text>
        </View>
        <View style={styles.headerRight}>
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
          <Text style={[styles.statusText, { color: statusColor }]}>{statusText}</Text>
        </View>
      </View>

      <View style={styles.terminalContainer}>
        <View style={styles.terminalHeader}>
          <View style={styles.terminalDots}>
            <View style={[styles.dot, { backgroundColor: '#ff5f56' }]} />
            <View style={[styles.dot, { backgroundColor: '#ffbd2e' }]} />
            <View style={[styles.dot, { backgroundColor: '#27ca40' }]} />
          </View>
          <Text style={styles.terminalTitle}>genesis@omega:~</Text>
        </View>

        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={({ item }) => <TerminalMessage message={item} isUser={item.role === 'user'} />}
          keyExtractor={item => item.id}
          contentContainerStyle={styles.messagesList}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>// Genesis Protocol v2.0</Text>
              <Text style={styles.emptyText}>// Awaiting input...</Text>
              <Text style={styles.emptyText}>// Type your command below_</Text>
            </View>
          }
        />

        {isLoading && <LoadingDots />}
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        <View style={styles.inputContainer}>
          <Text style={styles.inputPrompt}>$</Text>
          <TextInput
            style={styles.input}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Enter command..."
            placeholderTextColor="#666"
            autoCapitalize="none"
            autoCorrect={false}
            onSubmitEditing={sendMessage}
            returnKeyType="send"
            editable={!isLoading}
          />
          <TouchableOpacity style={[styles.sendButton, isLoading && styles.sendButtonDisabled]} onPress={sendMessage} disabled={isLoading || !inputText.trim()}>
            <Text style={styles.sendButtonText}>▶</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a1a',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#00ff88',
    letterSpacing: 4,
  },
  subtitle: {
    fontSize: 12,
    color: '#00ff88',
    opacity: 0.6,
    marginLeft: 8,
    letterSpacing: 2,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  statusText: {
    fontSize: 10,
    fontWeight: 'bold',
    letterSpacing: 1,
  },
  terminalContainer: {
    flex: 1,
    margin: 8,
    borderRadius: 8,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#1a1a1a',
  },
  terminalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    backgroundColor: '#1a1a1a',
  },
  terminalDots: {
    flexDirection: 'row',
    marginRight: 12,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 6,
  },
  terminalTitle: {
    color: '#666',
    fontSize: 12,
  },
  messagesList: {
    padding: 12,
    flexGrow: 1,
  },
  messageRow: {
    flexDirection: 'row',
    marginBottom: 12,
    alignItems: 'flex-start',
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  genesisRow: {
    justifyContent: 'flex-start',
  },
  prompt: {
    color: '#00ff88',
    fontSize: 16,
    fontWeight: 'bold',
    marginRight: 8,
    width: 20,
  },
  messageBox: {
    maxWidth: '75%',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 4,
  },
  userBox: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#00ff88',
  },
  genesisBox: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#333',
  },
  messageText: {
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 20,
  },
  cursor: {
    color: '#00ff88',
    fontSize: 14,
  },
  loadingRow: {
    flexDirection: 'row',
    padding: 12,
    alignItems: 'center',
  },
  loadingText: {
    color: '#666',
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 100,
  },
  emptyText: {
    color: '#333',
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    marginVertical: 4,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#0a0a0a',
    borderTopWidth: 1,
    borderTopColor: '#1a1a1a',
  },
  inputPrompt: {
    color: '#00ff88',
    fontSize: 18,
    fontWeight: 'bold',
    marginRight: 8,
  },
  input: {
    flex: 1,
    color: '#ffffff',
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    paddingVertical: 8,
    paddingHorizontal: 12,
    backgroundColor: '#111',
    borderRadius: 4,
  },
  sendButton: {
    marginLeft: 10,
    padding: 10,
    backgroundColor: '#00ff88',
    borderRadius: 4,
  },
  sendButtonDisabled: {
    opacity: 0.3,
  },
  sendButtonText: {
    color: '#000',
    fontSize: 14,
    fontWeight: 'bold',
  },
});

export default ChatScreen;