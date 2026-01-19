const Chip = ({ label, value, isActive, onClick, allowMultiple = false }) => {
  return (
    <div
      className={`chip ${isActive ? 'chip-active' : ''}`}
      onClick={() => onClick(value)}
    >
      {label}
    </div>
  );
};

export const ChipGroup = ({ chips, selected, onChange, allowMultiple = false }) => {
  const handleClick = (value) => {
    if (allowMultiple) {
      // Toggle selection for multiple
      if (selected.includes(value)) {
        onChange(selected.filter((v) => v !== value));
      } else {
        onChange([...selected, value]);
      }
    } else {
      // Single selection
      onChange(value);
    }
  };

  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {chips.map((chip) => (
        <Chip
          key={chip.value}
          label={chip.label}
          value={chip.value}
          isActive={
            allowMultiple
              ? selected.includes(chip.value)
              : selected === chip.value
          }
          onClick={handleClick}
          allowMultiple={allowMultiple}
        />
      ))}
    </div>
  );
};

export default Chip;
