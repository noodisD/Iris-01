import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useApp } from '../../context/AppContext';
import api from '../../services/api';
import Message from './Message';
import ChatInput from './ChatInput';

const ChatContainer = () => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const chatContainerRef = useRef(null);

  const { token, user } = useAuth();
  const { showToast } = useApp();

  useEffect(() => {
    loadChatHistory();
  }, [token]);

  useEffect(() => {
    // Scroll to bottom when new messages are added
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const loadChatHistory = async () => {
    if (!token) return;

    try {
      const data = await api.getChatHistory(token);
      const formattedMessages = [];

      data.messages.forEach((msg) => {
        if (msg.user_message && !msg.user_message.startsWith('[IRIS noticed:')) {
          formattedMessages.push({
            text: msg.user_message,
            sender: 'user',
          });
        }
        if (msg.companion_response) {
          formattedMessages.push({
            text: msg.companion_response,
            sender: 'iris',
          });
        }
      });

      setMessages(formattedMessages);
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  };

  const handleSendMessage = async (message) => {
    if (!message.trim()) return;

    // Add user message immediately
    const userMessage = { text: message, sender: 'user' };
    setMessages((prev) => [...prev, userMessage]);

    setLoading(true);

    try {
      const data = await api.sendMessage(message, token);

      // Add IRIS response
      const irisMessage = { text: data.message, sender: 'iris' };
      setMessages((prev) => [...prev, irisMessage]);
    } catch (error) {
      showToast('Failed to send message. Please try again.', 'error');
      console.error('Chat error:', error);

      // Add error message
      const errorMessage = {
        text: `Error: ${error.message}`,
        sender: 'iris',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages Container */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto p-8 flex flex-col items-center gap-4"
      >
        {messages.length === 0 && (
          <div className="text-center text-text-secondary py-16">
            <p className="text-lg">
              Hello {user}. I'm IRIS, your personal AI companion.
              <br />
              Tell me what's on your mind.
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <Message key={idx} text={msg.text} sender={msg.sender} />
        ))}

        {loading && (
          <div className="text-text-secondary text-sm">IRIS is thinking...</div>
        )}
      </div>

      {/* Input Area */}
      <ChatInput onSend={handleSendMessage} disabled={loading} />
    </div>
  );
};

export default ChatContainer;
