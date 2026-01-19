// API Service Layer for IRIS Backend
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Demo mode mock data
const MOCK_DATA = {
  chatHistory: {
    messages: [
      { user_message: "Hello IRIS!", companion_response: "Hello! Welcome to the demo. I'm here to help you explore the interface." },
      { user_message: "How are you today?", companion_response: "I'm functioning well, thank you! This is demo mode, so I'm showing you sample responses. Connect to the backend to chat with the real AI." },
    ]
  },
  habits: [
    {
      id: 1,
      name: "Morning Meditation",
      habit_type: "completion",
      current_streak: 7,
      weekly_target: 0,
      weekly_progress: null,
    },
    {
      id: 2,
      name: "Reading",
      habit_type: "duration",
      current_streak: 3,
      weekly_target: 300,
      tracking_metric: "minutes",
      weekly_progress: { current: 180, target: 300, metric: "minutes", percent: 60 },
    },
    {
      id: 3,
      name: "Exercise",
      habit_type: "count",
      current_streak: 14,
      weekly_target: 7,
      tracking_metric: "times",
      weekly_progress: { current: 3, target: 7, metric: "times", percent: 43 },
    },
  ],
  weeklySummary: {
    habits: [
      { name: "Meditation", completed: 7, total_days: 7 },
      { name: "Reading", completed: 3, total_days: 5 },
      { name: "Exercise", completed: 5, total_days: 7 },
      { name: "Water Intake", completed: 6, total_days: 7 },
    ]
  },
  reflections: [
    {
      id: 1,
      reflection_date: "2026-01-19",
      content: "Today was a really productive day. I managed to finish the React migration and felt great about the clean component architecture. The new structure makes it so much easier to find and update code.",
      mood: "great",
      energy_level: 4,
    },
    {
      id: 2,
      reflection_date: "2026-01-18",
      content: "Feeling a bit anxious about the deadline, but I'm making steady progress. Need to remember to take breaks more often and not push myself too hard.",
      mood: "okay",
      energy_level: 3,
    },
  ],
  moodTrend: {
    mood_distribution: { great: 8, good: 5, okay: 4, bad: 2 },
    average_energy_level: 3.8,
  }
};

class ApiService {
  constructor() {
    this.baseUrl = API_URL;
    this.demoMode = false;
  }

  // Check if we're in demo mode
  isDemoMode(token) {
    return token === 'demo-token-12345' || localStorage.getItem('demo_mode') === 'true';
  }

  // Helper method for making requests
  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Request failed');
      }

      return data;
    } catch (error) {
      console.error('API Error:', error);
      throw error;
    }
  }

  // ============================================================
  // AUTH ENDPOINTS
  // ============================================================

  async signup(username, password) {
    return this.request('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  async login(username, password) {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  // ============================================================
  // CHAT ENDPOINTS
  // ============================================================

  async sendMessage(message, token) {
    if (this.isDemoMode(token)) {
      // Simulate delay
      await new Promise(resolve => setTimeout(resolve, 500));
      return {
        message: "This is a demo response. In the real app, I would analyze your message and provide personalized insights based on your patterns and history."
      };
    }
    return this.request('/chat/message', {
      method: 'POST',
      body: JSON.stringify({ message, token }),
    });
  }

  async getChatHistory(token) {
    if (this.isDemoMode(token)) {
      return MOCK_DATA.chatHistory;
    }
    return this.request('/chat/history', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  }

  async triggerProactive(token, actionType, details) {
    if (this.isDemoMode(token)) {
      return { message: '...' }; // No proactive in demo
    }
    return this.request('/chat/proactive', {
      method: 'POST',
      body: JSON.stringify({
        token,
        action_type: actionType,
        details,
      }),
    });
  }

  // ============================================================
  // HABITS ENDPOINTS
  // ============================================================

  async createHabit(token, habitData) {
    if (this.isDemoMode(token)) {
      await new Promise(resolve => setTimeout(resolve, 300));
      return { success: true };
    }
    return this.request(`/habits?token=${token}`, {
      method: 'POST',
      body: JSON.stringify(habitData),
    });
  }

  async getTodayHabits(token) {
    if (this.isDemoMode(token)) {
      return { habits: MOCK_DATA.habits };
    }
    return this.request(`/habits/today?token=${token}`);
  }

  async getWeeklySummary(token) {
    if (this.isDemoMode(token)) {
      return MOCK_DATA.weeklySummary;
    }
    return this.request(`/habits/weekly?token=${token}`);
  }

  async logHabitCompletion(token, habitId, value = 1.0) {
    if (this.isDemoMode(token)) {
      await new Promise(resolve => setTimeout(resolve, 300));
      return { success: true };
    }
    return this.request(`/habits/complete?token=${token}`, {
      method: 'POST',
      body: JSON.stringify({ habit_id: habitId, value }),
    });
  }

  async logHabitSkip(token, habitId, reason = '') {
    if (this.isDemoMode(token)) {
      await new Promise(resolve => setTimeout(resolve, 300));
      return { success: true };
    }
    return this.request(`/habits/skip?token=${token}`, {
      method: 'POST',
      body: JSON.stringify({ habit_id: habitId, reason }),
    });
  }

  // ============================================================
  // REFLECTIONS ENDPOINTS
  // ============================================================

  async createReflection(token, reflectionData) {
    if (this.isDemoMode(token)) {
      await new Promise(resolve => setTimeout(resolve, 300));
      return { success: true };
    }
    return this.request(`/reflections?token=${token}`, {
      method: 'POST',
      body: JSON.stringify(reflectionData),
    });
  }

  async getReflections(token, limit = 10) {
    if (this.isDemoMode(token)) {
      return { reflections: MOCK_DATA.reflections };
    }
    return this.request(`/reflections?token=${token}&limit=${limit}`);
  }

  async getMoodTrend(token, days = 30) {
    if (this.isDemoMode(token)) {
      return MOCK_DATA.moodTrend;
    }
    return this.request(`/reflections/moods?token=${token}&days=${days}`);
  }
}

// Export a singleton instance
export default new ApiService();
