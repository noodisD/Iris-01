import { useState } from 'react';

const ChatInput = ({ onSend, disabled }) => {
  const [message, setMessage] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSend(message);
      setMessage('');
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="w-full safe-bottom-padding">
      <form onSubmit={handleSubmit} className="relative group">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask Iris anything about your patterns..."
          className="input-field pr-24 py-4 rounded-2xl shadow-xl border-border-subtle focus:border-primary-amber transition-all duration-300"
          disabled={disabled}
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2">
          <button
            type="submit"
            className="btn-primary interactive-tactile py-2.5 px-6 rounded-xl text-sm disabled:grayscale disabled:opacity-50 transition-all"
            disabled={disabled || !message.trim()}
          >
            {disabled ? '...' : 'Send'}
          </button>
        </div>
      </form>
      <p className="text-[10px] text-text-muted mt-3 text-center uppercase tracking-[0.2em] font-bold opacity-40 selection:bg-primary-amber/30">
        Iris operates on evidence-based inference. Patterns may take time to emerge.
      </p>
    </div>
  );
};

export default ChatInput;
