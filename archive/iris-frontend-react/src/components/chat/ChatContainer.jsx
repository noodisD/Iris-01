import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useApp } from '../../context/AppContext';
import api from '../../services/api';
import Message from './Message';
import ChatInput from './ChatInput';

const ChatContainer = () => {
  const [messages, setMessages] = useState([]);
  const [greeting, setGreeting] = useState('');
  const [loading, setLoading] = useState(false);
  const chatContainerRef = useRef(null);

  const { token, user } = useAuth();
  const { showToast } = useApp();

  const loadChatHistory = useCallback(async () => {
    if (!token) return;

    try {
      const data = await api.getChatHistory(token);
      const formattedMessages = [];

      data.messages.forEach((msg, idx) => {
        if (msg.user_message && !msg.user_message.startsWith('[IRIS noticed:')) {
          formattedMessages.push({
            id: `user-${idx}-${Date.now()}`,
            text: msg.user_message,
            sender: 'user',
          });
        }
        if (msg.companion_response) {
          formattedMessages.push({
            id: `iris-${idx}-${Date.now()}`,
            text: msg.companion_response,
            sender: 'iris',
          });
        }
      });

      setMessages(formattedMessages);

      // If no messages, fetch a dynamic greeting
      if (formattedMessages.length === 0) {
        try {
          const greetingData = await api.getGreeting(token);
          setGreeting(greetingData.greeting);
        } catch (e) {
          setGreeting(`Hi, I'm Iris. I'm your personal companion. How are you doing today?`);
        }
      }
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  }, [token]);

  useEffect(() => {
    loadChatHistory();
  }, [loadChatHistory]);

  useEffect(() => {
    // Scroll to bottom when new messages are added
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const handleSendMessage = useCallback(async (message) => {
    if (!message.trim()) return;

    // Add user message immediately
    const userMessage = { 
      id: `user-new-${Date.now()}`, 
      text: message, 
      sender: 'user' 
    };
    setMessages((prev) => [...prev, userMessage]);

    setLoading(true);

    try {
      const data = await api.sendMessage(message, token);

      // Add IRIS response
      const irisMessage = { 
        id: `iris-new-${Date.now()}`, 
        text: data.message, 
        sender: 'iris' 
      };
      setMessages((prev) => [...prev, irisMessage]);
    } catch (error) {
      showToast('Failed to send message. Please try again.', 'error');
      console.error('Chat error:', error);

      // Add error message
      const errorMessage = {
        id: `iris-err-${Date.now()}`,
        text: `Error: ${error.message}`,
        sender: 'iris',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  }, [token, showToast]);

  return (
    <div className="flex flex-col h-full bg-bg-deep/30">
      {/* Messages Container */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto p-6 md:p-12 space-y-10 scroll-smooth custom-scrollbar"
      >
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center min-h-[60%] text-center px-6 animate-fade-in">
            <div className="w-20 h-20 bg-primary-amber/10 rounded-full flex items-center justify-center mb-8">
              <span className="text-4xl text-primary-amber animate-pulse">✨</span>
            </div>
            <h2 className="text-3xl font-black mb-3 text-gradient-gold">Iris</h2>
            <p className="text-text-secondary max-w-sm text-lg leading-relaxed">
              {greeting || '...'}
            </p>
          </div>
        )}

        <div className="max-w-5xl mx-auto w-full space-y-8">
          {messages.map((msg) => (
            <Message key={msg.id} text={msg.text} sender={msg.sender} />
          ))}

          {loading && (
            <div className="flex justify-start animate-fade-in ml-2">
              <div className="bg-bg-surface border border-border-subtle px-6 py-4 rounded-2xl rounded-tl-none flex items-center gap-4 shadow-xl">
                <div className="flex gap-1.5">
                  <div className="w-2 h-2 bg-primary-amber rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-primary-amber rounded-full animate-bounce [animation-delay:0.2s]"></div>
                  <div className="w-2 h-2 bg-primary-amber rounded-full animate-bounce [animation-delay:0.4s]"></div>
                </div>
                <span className="text-xs font-black uppercase tracking-[0.2em] text-primary-amber/70">IRIS IS PROCESSING</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input Area (Floating) */}
      <div className="max-w-5xl mx-auto w-full px-6 pb-10 pt-4">
        <ChatInput onSend={handleSendMessage} disabled={loading} />
      </div>
    </div>
  );
};

export default ChatContainer;
