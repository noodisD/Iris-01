// API Service Layer for IRIS Backend
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiService {
  constructor() {
    this.baseUrl = API_URL;
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
    return this.request('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  async login(username, password) {
    return this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  // ============================================================
  // CHAT ENDPOINTS
  // ============================================================

  async sendMessage(message, token) {
    return this.request('/api/chat/message', {
      method: 'POST',
      body: JSON.stringify({ message, token }),
    });
  }

  async getChatHistory(token) {
    return this.request('/api/chat/history', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  }

  async getGreeting(token) {
    return this.request('/api/chat/greeting', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
  }

  async triggerProactive(token, actionType, details) {
    return this.request('/api/chat/proactive', {
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
    return this.request(`/api/habits?token=${token}`, {
      method: 'POST',
      body: JSON.stringify(habitData),
    });
  }

  async getTodayHabits(token) {
    return this.request(`/api/habits/today?token=${token}`);
  }

  async getWeeklySummary(token) {
    return this.request(`/api/habits/weekly?token=${token}`);
  }

  async logHabitCompletion(token, habitId, value = 1.0) {
    return this.request(`/api/habits/complete?token=${token}`, {
      method: 'POST',
      body: JSON.stringify({ habit_id: habitId, value }),
    });
  }

  async logHabitSkip(token, habitId, reason = '') {
    return this.request(`/api/habits/skip?token=${token}`, {
      method: 'POST',
      body: JSON.stringify({ habit_id: habitId, reason }),
    });
  }

  // ============================================================
  // REFLECTIONS ENDPOINTS
  // ============================================================

  async createReflection(token, reflectionData) {
    return this.request(`/api/reflections?token=${token}`, {
      method: 'POST',
      body: JSON.stringify(reflectionData),
    });
  }

  async getReflections(token, limit = 10) {
    return this.request(`/api/reflections?token=${token}&limit=${limit}`);
  }

  async getMoodTrend(token, days = 30) {
    return this.request(`/api/reflections/moods?token=${token}&days=${days}`);
  }
}

// Export a singleton instance
export default new ApiService();