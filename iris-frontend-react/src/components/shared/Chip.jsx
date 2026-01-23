const Chip = ({ label, value, isActive, onClick }) => {
  return (
    <button
      type="button"
      className={`chip ${isActive ? 'chip-active' : ''} interactive-tactile cursor-pointer pointer-events-auto transition-all duration-200`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick(value);
      }}
    >
      {label}
    </button>
  );
};

export const ChipGroup = ({ chips, selected, onChange, allowMultiple = false }) => {
  const handleClick = (value) => {
    if (allowMultiple) {
      const currentSelected = Array.isArray(selected) ? selected : [];
      if (currentSelected.some(v => v == value)) {
        onChange(currentSelected.filter((v) => v != value));
      } else {
        onChange([...currentSelected, value]);
      }
    } else {
      onChange(value);
    }
  };

  return (
    <div className="flex flex-wrap gap-2 mt-2 py-1">
      {chips.map((chip) => (
        <Chip
          key={String(chip.value)}
          label={chip.label}
          value={chip.value}
          isActive={
            allowMultiple
              ? (Array.isArray(selected) && selected.some(v => v == chip.value))
              : selected == chip.value
          }
          onClick={handleClick}
        />
      ))}
    </div>
  );
};

export default Chip;
