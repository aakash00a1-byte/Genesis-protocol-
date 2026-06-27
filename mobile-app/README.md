# Genesis Protocol Mobile App

**Autonomous AI Agent Mobile Application**

## 📱 Overview

Genesis Protocol Mobile App connects to your Genesis Protocol backend running on Railway, providing real-time monitoring, chat, and control of your autonomous AI agent from your mobile device.

## ✨ Features

- **📊 Live Dashboard** - Real-time system status and statistics
- **💬 AI Chat** - Direct chat interface with Genesis AI
- **📝 Activity Log** - Track all system events and actions
- **💜 Discord Integration** - Monitor and control Discord bot
- **🔔 Push Notifications** - Instant alerts for important events
- **🔐 Secure Login** - Biometric authentication support
- **📡 Offline Mode** - Cached data for offline access
- **🌙 Dark Mode** - Beautiful dark theme UI

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Genesis Mobile App                     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │Dashboard │  │   Chat   │  │Activity  │  │ Settings │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │             │             │             │       │
│       └─────────────┴──────┬──────┴─────────────┘       │
│                            │                             │
│                    ┌───────┴───────┐                     │
│                    │  API Client   │                     │
│                    │  (Axios)      │                     │
│                    └───────┬───────┘                     │
│                            │                             │
└────────────────────────────┼─────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              Railway Backend (Genesis)                   │
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐│
│  │ Telegram │  │ Discord  │  │   Web    │  │   AI     ││
│  │   Bot    │  │   Bot    │  │   API    │  │  Chain   ││
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘│
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- npm or yarn
- Expo CLI (`npx expo start`)
- EAS Build CLI (for building) (`npm i -g eas-cli`)

### Installation

```bash
# Navigate to mobile app directory
cd mobile-app

# Install dependencies
npm install

# Start development server
npm start
```

### Running on Devices

```bash
# iOS Simulator
npx expo run:ios

# Android Emulator
npx expo run:android

# Physical Device (requires EAS)
eas build --profile preview --platform android
```

## 📦 Project Structure

```
mobile-app/
├── src/
│   ├── api/           # API client and services
│   ├── components/     # Reusable UI components
│   ├── context/        # React contexts (Auth, Theme)
│   ├── hooks/          # Custom React hooks
│   ├── navigation/     # Navigation configuration
│   ├── screens/        # Screen components
│   ├── store/          # State management
│   ├── types/          # TypeScript types
│   └── utils/          # Utility functions
├── App.tsx             # App entry point
├── app.json           # Expo configuration
├── eas.json           # EAS Build configuration
└── package.json       # Dependencies
```

## ⚙️ Configuration

### Backend URL

Update the backend URL in `src/api/config.ts`:

```typescript
export const API_CONFIG = {
  BASE_URL: 'https://your-railway-url.up.railway.app',
  // ...
};
```

### Environment Variables

Create a `.env` file:

```
API_URL=https://genesis-protocol-00a1.up.railway.app
```

## 🔒 Security Features

- **Secure Storage** - API keys and tokens stored in device secure storage
- **Biometric Auth** - Optional fingerprint/Face ID login
- **Offline Queue** - Encrypted queue for offline actions
- **Auto-logout** - Session timeout after inactivity

## 📲 Building for Production

### Android (APK/AAB)

```bash
# Configure EAS
eas build:configure

# Build APK for testing
eas build --profile preview --platform android

# Build AAB for Play Store
eas build --profile production --platform android
```

### iOS

```bash
# Configure EAS
eas build:configure

# Build for iOS
eas build --profile production --platform ios
```

## 🔔 Push Notifications

The app uses Expo Notifications for push alerts. Configure in `app.json`:

```json
{
  "plugins": [
    [
      "expo-notifications",
      {
        "icon": "./assets/notification-icon.png",
        "color": "#00ff88"
      }
    ]
  ]
}
```

## 🌐 API Integration

The mobile app connects to these backend endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/chat` | POST | Send message to Genesis |
| `/api/v1/chat/history` | GET | Get chat history |
| `/api/v1/status` | GET | System status |
| `/api/v1/health` | GET | Health check |
| `/api/v1/discord/status` | GET | Discord bot status |
| `/api/v1/activity/logs` | GET | Activity logs |

## 📱 Screenshots

The app features:
- Dark cyberpunk-inspired theme
- Real-time system monitoring
- Smooth animations
- Intuitive navigation

## 🐛 Troubleshooting

### App Won't Connect to Backend
1. Check backend URL in `src/api/config.ts`
2. Verify backend is running on Railway
3. Check network connectivity

### Build Fails
1. Run `npx expo doctor` to check dependencies
2. Clear cache: `expo start --clear`
3. Reinstall node_modules

### Notifications Not Working
1. Check notification permissions on device
2. Verify FCM/APNs credentials
3. Check notification service is running

## 📄 License

MIT License - See LICENSE file for details.

---

**Built with ❤️ using Expo & React Native**

**Genesis Protocol - Autonomous AI Agent**
