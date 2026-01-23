import { memo } from 'react';

const ReflectionItem = memo(({ reflection }) => {
  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown date';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const truncateContent = (text, maxLength = 300) => {
    if (!text) return 'No content provided';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  return (
    <div className="card-insight p-5 animate-fade-in">
      <div className="flex justify-between items-start mb-3">
        <div className="text-xs font-medium text-text-muted uppercase tracking-wider">
          {formatDate(reflection.reflection_date)}
        </div>
        <div className="flex gap-2">
          {reflection.mood && (
            <span className="badge">
              {reflection.mood}
            </span>
          )}
        </div>
      </div>

      <div className="text-text-primary text-base leading-relaxed mb-4">
        {truncateContent(reflection.content)}
      </div>

      <div className="flex items-center gap-4">
        {reflection.energy_level && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-secondary font-medium uppercase tracking-tighter">Energy</span>
            <div className="flex gap-1">
              {[...Array(5)].map((_, i) => (
                <div 
                  key={i} 
                  className={`w-2 h-2 rounded-full ${i < reflection.energy_level ? 'bg-primary-amber' : 'bg-border-subtle'}`}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

ReflectionItem.displayName = 'ReflectionItem';

export default ReflectionItem;
