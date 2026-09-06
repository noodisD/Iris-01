import { memo } from 'react';

const Message = memo(({ text, sender }) => {
  const isIris = sender === 'iris';

  return (
    <div
      className={`w-full flex ${isIris ? 'justify-start' : 'justify-end'} animate-fade-in mb-8`}
    >
      <div
        className={`max-w-[85%] md:max-w-2xl p-[var(--spacing-card-padding)] rounded-2xl text-sm md:text-base leading-relaxed shadow-sm ${
          isIris
            ? 'bg-bg-surface text-text-primary border border-border-subtle rounded-tl-none'
            : 'bg-gradient-to-br from-primary-amber to-primary-gold text-black font-medium rounded-tr-none'
        }`}
      >
        {isIris && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <div className="w-4 h-4 bg-primary-gold rounded-sm flex items-center justify-center text-[10px] font-bold text-black">
              I
            </div>
            <span className="text-[10px] font-black uppercase tracking-widest text-primary-amber">Iris Inference</span>
          </div>
        )}
        <div className="whitespace-pre-wrap">{text}</div>
      </div>
    </div>
  );
});

Message.displayName = 'Message';

export default Message;
