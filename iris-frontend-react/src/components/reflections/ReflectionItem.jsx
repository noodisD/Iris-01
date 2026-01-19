const ReflectionItem = ({ reflection }) => {
  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const truncateContent = (text, maxLength = 200) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  return (
    <div className="card p-4">
      <div className="text-xs text-text-secondary mb-2">
        {formatDate(reflection.reflection_date)}
      </div>

      <div className="text-text-primary leading-relaxed mb-3">
        {truncateContent(reflection.content)}
      </div>

      <div className="flex gap-3 flex-wrap text-xs">
        {reflection.mood && (
          <span className="bg-primary-gold/10 text-text-secondary px-3 py-1 rounded">
            Mood: {reflection.mood}
          </span>
        )}
        {reflection.energy_level && (
          <span className="bg-primary-gold/10 text-text-secondary px-3 py-1 rounded">
            Energy: {reflection.energy_level}/5
          </span>
        )}
      </div>
    </div>
  );
};

export default ReflectionItem;
