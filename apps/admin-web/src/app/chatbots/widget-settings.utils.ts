export const DEFAULT_WIDGET_COLOR = "#1463ff";
export const validWidgetColor = (value: string) => /^#[0-9a-f]{6}$/i.test(value);

export function widgetForeground(hex: string): string {
  const color = validWidgetColor(hex) ? hex : DEFAULT_WIDGET_COLOR;
  const rgb = [1, 3, 5].map((start) => {
    const v = parseInt(color.slice(start, start + 2), 16) / 255;
    return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
  });
  const l = rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  return (l + .05) / .05 > 1.05 / (l + .05) ? "#000000" : "#ffffff";
}

export function parseWidgetOrigins(text: string): { origins: string[]; error: string } {
  const origins: string[] = [];
  for (const value of text.split(/\n|,/).map((v) => v.trim()).filter(Boolean)) {
    try {
      const url = new URL(value);
      if (!/^https?:$/.test(url.protocol) || !url.hostname || url.username || url.password ||
          url.pathname !== "/" || /[?#\\*\s]/.test(value) || url.port === "0") throw new Error();
      if (!origins.includes(url.origin)) origins.push(url.origin);
    } catch {
      return { origins, error: `Origin không hợp lệ: ${value}. Chỉ nhập http(s)://host[:port], không kèm đường dẫn.` };
    }
  }
  return { origins, error: !origins.length ? "Nhập ít nhất một website được phép." : origins.length > 20 ? "Tối đa 20 origins." : "" };
}
