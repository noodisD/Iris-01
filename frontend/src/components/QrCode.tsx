import { useEffect, useState } from 'react';
import QRCode from 'qrcode';

export function QrCode({ value, label }: { value: string; label: string }) {
  const [image, setImage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    setImage(null);
    setFailed(false);
    QRCode.toString(value, { type: 'svg', errorCorrectionLevel: 'M', margin: 1 })
      .then((svg) => {
        if (active) setImage('data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg));
      })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [value]);

  if (failed) return <div role="alert">Could not draw the QR code; use the values shown instead.</div>;
  return image ? <img src={image} width={220} height={220} alt={label} /> : null;
}
