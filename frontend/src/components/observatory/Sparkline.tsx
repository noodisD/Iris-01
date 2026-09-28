export function Sparkline({ values, marks, label, width = 120, height = 28 }: {
  values: (number | null)[];
  marks?: boolean[];
  label: string;
  width?: number;
  height?: number;
}) {
  const nums = values.map(value => value ?? 0);
  const max = Math.max(...nums, 1);
  const step = nums.length > 1 ? width / (nums.length - 1) : width;
  const points = nums.map((value, index) => `${index * step},${height - (value / max) * (height - 2) - 1}`).join(' ');
  return (
    <svg className="obs-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <polyline fill="none" stroke="var(--petal-3)" strokeWidth="1.5" points={points} />
      {marks?.map((marked, index) => marked ? (
        <circle key={index} cx={index * step} cy={height - (nums[index] / max) * (height - 2) - 1} r="2" fill="var(--worse)" />
      ) : null)}
    </svg>
  );
}
